"""Real Authlib code/state/PKCE/JWKS verification against a signed test issuer.

This is an isolated protocol fixture, not a replacement for Keycloak integration.
"""
import base64
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from django.conf import settings
from django.test import TestCase, override_settings
from joserfc import jwt
from joserfc.jwk import RSAKey
from identity.models import OIDCIdentity, PatientWorkspace, Person, User


class OIDCTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = RSAKey.generate_key(parameters={'kid': 'fixture-key'})
        cls.other_key = RSAKey.generate_key(parameters={'kid': 'fixture-key'})
        fixture = cls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send_json(self, body, status=200):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path.endswith('/certs'):
                    self.send_json({'keys': [fixture.key.as_dict()]})
                else:
                    self.send_json({'error': 'unexpected_path'}, 404)
            def do_POST(self):
                fixture.token_requests += 1
                params = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode())
                verifier = params.get('code_verifier', [''])[0]
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                expected_auth = 'Basic ' + base64.b64encode(b'fixture-client:fixture-secret').decode()
                if (challenge != fixture.challenge or params.get('code') != ['fixture-code']
                        or self.headers.get('Authorization') != expected_auth):
                    self.send_json({'error': 'invalid_grant'}, 400)
                    return
                fixture.pkce_verified = True
                fixture.redirect_verified = params.get('redirect_uri') == [settings.APP_BASE_URL + '/auth/callback/']
                now = int(time.time())
                claims = {'iss': fixture.issuer, 'sub': 'alice', 'aud': 'fixture-client',
                          'iat': now, 'exp': now + 300, 'nonce': fixture.nonce, 'name': 'Alice'}
                claims.update(fixture.claim_overrides)
                if fixture.missing_claim:
                    del claims[fixture.missing_claim]
                key = fixture.other_key if fixture.bad_signature else fixture.key
                encoded = jwt.encode({'alg': 'RS256', 'kid': 'fixture-key'}, claims, key)
                body = {'access_token': 'fixture-access-token', 'token_type': 'Bearer', 'expires_in': 300}
                if not fixture.omit_id_token:
                    body['id_token'] = encoded
                self.send_json(body)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.issuer = f'http://127.0.0.1:{cls.server.server_port}/realms/continuity'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.config = override_settings(
            OIDC_ISSUER=cls.issuer, OIDC_INTERNAL_ISSUER=cls.issuer,
            OIDC_CLIENT_ID='fixture-client', OIDC_CLIENT_SECRET='fixture-secret',
        )
        cls.config.enable()

    @classmethod
    def tearDownClass(cls):
        cls.config.disable()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        super().tearDownClass()

    def setUp(self):
        type(self).token_requests = 0
        type(self).claim_overrides = {}
        type(self).missing_claim = None
        type(self).bad_signature = False
        type(self).omit_id_token = False
        type(self).pkce_verified = False
        type(self).redirect_verified = False

    def begin(self):
        response = self.client.post('/auth/login/')
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlsplit(response['Location']).query)
        self.assertEqual(params['code_challenge_method'], ['S256'])
        self.assertEqual(params['response_type'], ['code'])
        self.assertIn('openid', params['scope'][0])
        type(self).nonce = params['nonce'][0]
        type(self).challenge = params['code_challenge'][0]
        return params['state'][0]

    def complete(self, state, **extra):
        return self.client.get('/auth/callback/', {'state': state, 'code': 'fixture-code', **extra})

    def test_verified_oidc_creates_empty_workspace_with_pkce_and_rotates_session(self):
        state = self.begin()
        old_session = self.client.session.session_key
        response = self.complete(state)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(type(self).pkce_verified)
        self.assertTrue(type(self).redirect_verified)
        self.assertNotEqual(self.client.session.session_key, old_session)
        self.assertNotIn('id_token', self.client.session)
        self.assertNotIn('access_token', self.client.session)
        self.assertNotIn('refresh_token', self.client.session)
        self.assertEqual(User.objects.count(), 1)
        workspace = PatientWorkspace.objects.get()
        page = self.client.get(f'/workspaces/{workspace.pk}/')
        self.assertContains(page, 'Your records, ready for your next visit.')
        self.assertEqual(self.client.get(f'/api/workspaces/{workspace.pk}/records/').json()['records'], [])

    def test_wrong_state_rejected_before_token_exchange(self):
        self.begin()
        self.assertEqual(self.complete('unrecognized-state').status_code, 400)
        self.assertEqual(type(self).token_requests, 0)
        self.assertEqual(User.objects.count(), 0)

    def test_callback_replay_does_not_exchange_again(self):
        state = self.begin()
        self.assertEqual(self.complete(state).status_code, 302)
        self.assertEqual(self.complete(state).status_code, 400)
        self.assertEqual(type(self).token_requests, 1)
        self.assertEqual(User.objects.count(), 1)

    def test_expired_signin_attempt_rejected(self):
        state = self.begin()
        session = self.client.session
        session['_state_keycloak_' + state]['exp'] = time.time() - 1
        session.save()
        self.assertEqual(self.complete(state).status_code, 400)
        self.assertEqual(type(self).token_requests, 0)

    def test_invalid_signed_claims_rejected(self):
        for overrides in ({'iss': 'https://untrusted.example'}, {'aud': 'another-client'},
                          {'nonce': 'wrong'}, {'nonce': 'wrong', 'nonce_supported': False},
                          {'exp': int(time.time()) - 30}, {'sub': ''}):
            with self.subTest(overrides=overrides):
                state = self.begin()
                type(self).claim_overrides = overrides
                self.assertEqual(self.complete(state).status_code, 400)
                self.assertEqual(User.objects.count(), 0)

    def test_invalid_signature_rejected(self):
        state = self.begin()
        type(self).bad_signature = True
        self.assertEqual(self.complete(state).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_missing_id_token_or_mandatory_claim_rejected(self):
        state = self.begin()
        type(self).omit_id_token = True
        self.assertEqual(self.complete(state).status_code, 400)
        type(self).omit_id_token = False
        for claim in ('sub', 'exp', 'nonce'):
            state = self.begin()
            type(self).missing_claim = claim
            self.assertEqual(self.complete(state).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_wrong_authorization_issuer_and_bad_pkce_rejected(self):
        state = self.begin()
        self.assertEqual(self.complete(state, iss='https://wrong.example').status_code, 400)
        self.assertEqual(type(self).token_requests, 0)
        state = self.begin()
        type(self).challenge = 'incorrect-challenge'
        self.assertEqual(self.complete(state).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_email_never_merges_patients_and_provider_roles_are_ignored(self):
        for subject in ('alice', 'bob'):
            state = self.begin()
            type(self).claim_overrides = {'sub': subject, 'email': 'same@example.test', 'realm_access': {'roles': ['admin', 'clinician']}}
            self.assertEqual(self.complete(state).status_code, 302)
            self.client.post('/auth/logout/')
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Person.objects.count(), 2)
        self.assertEqual(PatientWorkspace.objects.count(), 2)
        self.assertEqual(OIDCIdentity.objects.count(), 2)

    def test_repeated_login_does_not_restore_revoked_access(self):
        state = self.begin()
        self.complete(state)
        from identity.models import WorkspaceMembership
        WorkspaceMembership.objects.update(status='revoked')
        self.client.post('/auth/logout/')
        state = self.begin()
        self.assertEqual(self.complete(state).status_code, 302)
        self.assertContains(self.client.get('/workspaces/'), 'No workspace is available')
        self.assertEqual(PatientWorkspace.objects.count(), 1)

    def test_provider_error_does_not_echo_untrusted_description(self):
        state = self.begin()
        response = self.complete(state, error='access_denied', error_description='sensitive-provider-payload')
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, 'sensitive-provider-payload', status_code=400)
        self.assertEqual(type(self).token_requests, 0)
