import time
from django.test import TestCase, Client
from django.utils import timezone
from identity.models import PatientWorkspace, AccessCapability, PatientPersonalDetails, WorkspaceMembership
from identity.services import resolve_verified_identity


class FrontendBootstrapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice=resolve_verified_identity('https://test.example/issuer','frontend-alice','Alice')
        cls.bob=resolve_verified_identity('https://test.example/issuer','frontend-bob','Bob')
        cls.workspace=PatientWorkspace.objects.get(subject_patient__person=cls.alice.person)

    def sign_in(self):
        self.client.force_login(self.alice,backend='identity.backends.OIDCSessionBackend')
        session=self.client.session
        session['oidc_expires_at']=int(time.time())+300
        session.save()

    def test_anonymous_and_expired_sessions_reveal_no_context(self):
        self.assertEqual(self.client.get('/api/session/').status_code,401)
        self.sign_in()
        session=self.client.session; session['oidc_expires_at']=0; session.save()
        self.assertEqual(self.client.get('/api/session/').json(),{'error':'sign_in_required'})

    def test_bootstrap_is_minimal_live_and_cross_patient_isolated(self):
        self.sign_in()
        PatientPersonalDetails.objects.create(workspace=self.workspace,preferred_name='Al',full_name='Private Name',email='private@example.invalid',identifier_type='national_id',identifier_number='PRIVATE-ID',updated_by=self.alice)
        response=self.client.get('/api/session/')
        data=response.json()
        self.assertEqual(data['contexts'][0]['patient_display_name'],'Al')
        self.assertEqual(data['contexts'][0]['workspace_id'],str(self.workspace.pk))
        self.assertEqual(len(data['contexts']),1)
        self.assertNotContains(response,'PRIVATE-ID'); self.assertNotContains(response,'private@example.invalid')
        self.assertEqual(response['Cache-Control'],'no-store, private')
        self.assertIn('csrftoken',response.cookies)
        AccessCapability.objects.filter(workspace=self.workspace,rule__capability_key='upload_source').update(revoked_at=timezone.now())
        self.assertNotIn('upload_source',self.client.get('/api/session/').json()['contexts'][0]['capabilities'])
        AccessCapability.objects.filter(workspace=self.workspace,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get('/api/session/').json()['contexts'],[])

    def test_relationship_or_staff_flag_does_not_create_a_context(self):
        self.sign_in()
        foreign=PatientWorkspace.objects.get(subject_patient__person=self.bob.person)
        WorkspaceMembership.objects.create(workspace=foreign,user=self.alice,relationship_type='caregiver',authority_basis='relationship_only')
        WorkspaceMembership.objects.create(workspace=foreign,user=self.alice,relationship_type='guardian',authority_basis='verified_guardianship',authority_reference='fictional test reference')
        self.assertEqual(len(self.client.get('/api/session/').json()['contexts']),1)

    def test_session_csrf_can_authorize_post_but_missing_token_cannot(self):
        self.sign_in()
        secured=Client(enforce_csrf_checks=True)
        secured.cookies=self.client.cookies
        token=secured.get('/api/session/').json()['csrf_token']
        url=f'/api/workspaces/{self.workspace.pk}/records/search/'
        self.assertEqual(secured.post(url,{'q':''},content_type='application/json').status_code,403)
        self.assertEqual(secured.post(url,{'q':''},content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,200)
