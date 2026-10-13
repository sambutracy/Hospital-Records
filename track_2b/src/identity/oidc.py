"""Pinned Keycloak endpoints; browser and server use different network addresses."""
from authlib.integrations.django_client import OAuth
from django.conf import settings


def keycloak_client():
    oauth = OAuth()
    public = settings.OIDC_ISSUER + '/protocol/openid-connect'
    internal = settings.OIDC_INTERNAL_ISSUER + '/protocol/openid-connect'
    client = oauth.register(
        'keycloak', client_id=settings.OIDC_CLIENT_ID, client_secret=settings.OIDC_CLIENT_SECRET,
        authorize_url=public + '/auth', access_token_url=internal + '/token',
        issuer=settings.OIDC_ISSUER, jwks_uri=internal + '/certs',
        end_session_endpoint=public + '/logout',
        id_token_signing_alg_values_supported=['RS256'],
        client_kwargs={
            'scope': 'openid profile', 'code_challenge_method': 'S256',
            'token_endpoint_auth_method': 'client_secret_basic', 'timeout': 10,
        },
    )
    client.framework.expires_in = 600
    return client
