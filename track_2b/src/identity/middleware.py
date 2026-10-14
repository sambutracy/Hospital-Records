import time
from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth import logout
from .models import AuditEvent


class AuthenticationLifetimeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        issuer = urlsplit(settings.OIDC_ISSUER)
        # Chrome applies form-action to the redirect after the local login POST.
        self.form_action = f"'self' {issuer.scheme}://{issuer.netloc}"

    def __call__(self, request):
        if request.user.is_authenticated:
            expiry = request.session.get('oidc_expires_at')
            if not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or expiry <= time.time():
                AuditEvent.objects.create(actor_user=request.user, action='session.expired', decision='deny')
                logout(request)
        elif request.session.get('_auth_user_id'):
            # The session backend rejected a disabled account/person.
            logout(request)
        response = self.get_response(request)
        response['Cache-Control'] = 'no-store, private'
        response['Content-Security-Policy'] = (
            "default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self'; script-src 'self'; connect-src 'self'; "
            f"form-action {self.form_action}; frame-ancestors 'none'; base-uri 'none'"
        )
        return response
