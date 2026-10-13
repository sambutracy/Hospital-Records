import time
from authlib.integrations.base_client.errors import OAuthError
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from joserfc.errors import JoseError
from requests.exceptions import RequestException
from .authorization import authorized_workspaces
from .models import AuditEvent
from .oidc import keycloak_client
from .services import resolve_verified_identity


@require_GET
def landing(request):
    if request.user.is_authenticated:
        return redirect('workspace_list')
    return render(request, 'landing.html', {'demo_mode': settings.DEMO_MODE})


@require_POST
def oidc_login(request):
    if request.user.is_authenticated:
        return redirect('workspace_list')
    request.session.cycle_key()
    # Only one outstanding sign-in attempt per browser session.
    for key in list(request.session.keys()):
        if key.startswith('_state_keycloak_'):
            del request.session[key]
    try:
        return keycloak_client().authorize_redirect(request, settings.APP_BASE_URL + '/auth/callback/')
    except (OAuthError, RequestException):
        return render(request, 'auth_error.html', {'message': 'Sign-in is temporarily unavailable. Please try again.'}, status=503)


@require_GET
def oidc_callback(request):
    client = keycloak_client()
    state = request.GET.get('state', '')
    saved = client.framework.get_state_data(request.session, state)
    try:
        envelope = request.session.get('_state_keycloak_' + state, {})
        if (not saved or not saved.get('nonce') or not saved.get('code_verifier')
                or envelope.get('exp', 0) <= time.time()):
            raise ValueError('Missing sign-in state')
        if request.GET.get('iss', settings.OIDC_ISSUER) != settings.OIDC_ISSUER:
            raise ValueError('Unexpected authorization issuer')
        token = client.authorize_access_token(request, claims_options={
            'iss': {'essential': True, 'values': [settings.OIDC_ISSUER]},
            'sub': {'essential': True}, 'aud': {'essential': True},
            'exp': {'essential': True}, 'iat': {'essential': True},
            'nonce': {'essential': True, 'value': saved['nonce']},
        }, leeway=0)
        claims = token.get('userinfo')
        if not claims or claims.get('iss') != settings.OIDC_ISSUER or claims.get('nonce') != saved['nonce']:
            raise ValueError('Invalid identity claims')
        subject = claims.get('sub')
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError('Invalid subject')
        expiry = min(int(claims['exp']), int(time.time()) + settings.SESSION_COOKIE_AGE)
        if expiry <= time.time():
            raise ValueError('Expired identity')
        display_name = claims.get('name') or claims.get('preferred_username') or 'Patient'
        if not isinstance(display_name, str):
            display_name = 'Patient'
        user = resolve_verified_identity(settings.OIDC_ISSUER, subject, display_name)
    except PermissionDenied:
        return render(request, 'auth_error.html', {'message': 'This account is unavailable. Contact the project administrator.'}, status=403)
    except (OAuthError, JoseError, RequestException, ValueError, KeyError, TypeError):
        client.framework.clear_state_data(request.session, state)
        AuditEvent.objects.create(action='sign_in.failed', decision='deny')
        # Never render/log provider descriptions, codes, tokens or claim payloads.
        return render(request, 'auth_error.html', {'message': 'Sign-in could not be completed. Please start again.'}, status=400)
    login(request, user, backend='identity.backends.OIDCSessionBackend')
    request.session['oidc_expires_at'] = expiry
    request.session.set_expiry(max(1, expiry - int(time.time())))
    AuditEvent.objects.create(actor_user=user, action='sign_in.completed', decision='allow')
    return redirect('workspace_list')


@require_POST
def sign_out(request):
    if request.user.is_authenticated:
        AuditEvent.objects.create(actor_user=request.user, action='sign_out', decision='allow')
    logout(request)  # Local session is invalidated before the provider redirect.
    return keycloak_client().logout_redirect(
        request, post_logout_redirect_uri=settings.APP_BASE_URL + '/auth/logged-out/',
        client_id=settings.OIDC_CLIENT_ID,
    )


@require_GET
def logged_out(request):
    if request.GET.get('state'):
        try:
            keycloak_client().validate_logout_response(request)
        except OAuthError:
            return render(request, 'auth_error.html', {'message': 'Your local session has ended. You can sign in again.'}, status=400)
    return render(request, 'logged_out.html')


@require_GET
@login_required
def workspace_list(request):
    workspaces = list(authorized_workspaces(request.user))
    if len(workspaces) == 1:
        return redirect('workspace_home', workspace_id=workspaces[0].id)
    return render(request, 'workspace_list.html', {'workspaces': workspaces})


@require_GET
@login_required
def workspace_home(request, workspace_id):
    workspace = authorized_workspaces(request.user).filter(pk=workspace_id).first()
    if not workspace:
        AuditEvent.objects.create(
            actor_user=request.user, action='workspace.open', decision='deny',
            target_type='patient_workspace', target_id=workspace_id,
        )
        raise Http404
    AuditEvent.objects.create(
        actor_user=request.user, workspace=workspace, action='workspace.open', decision='allow',
        target_type='patient_workspace', target_id=workspace.id,
    )
    return render(request, 'workspace_home.html', {'workspace': workspace})


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})
