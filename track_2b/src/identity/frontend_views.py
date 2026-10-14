"""Same-origin application shell and live authority bootstrap (contract v1)."""
import json
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from .authorization import SELF_ACTIONS, authorized_workspaces, effective_capabilities
from .models import PatientPersonalDetails


@require_GET
@ensure_csrf_cookie
def session(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'sign_in_required'}, status=401)
    contexts = []
    for workspace in authorized_workspaces(request.user).order_by('id'):
        profile = PatientPersonalDetails.objects.filter(workspace=workspace).first()
        name = ((profile.preferred_name or profile.full_name) if profile else '') or workspace.subject_patient.person.display_name
        capabilities = [action for action in SELF_ACTIONS if effective_capabilities(request.user, action).filter(workspace=workspace).exists()]
        contexts.append({'id': str(workspace.pk), 'workspace_id': str(workspace.pk),
                         'kind': 'patient', 'label': 'My health', 'patient_display_name': name,
                         'capacity': 'Self', 'capabilities': capabilities})
    return JsonResponse({'contract_version': 1, 'actor': {'id': str(request.user.pk),
                         'display_name': request.user.person.display_name}, 'contexts': contexts,
                         'default_context_id': contexts[0]['id'] if len(contexts) == 1 else None,
                         'expires_at': request.session['oidc_expires_at'],
                         'csrf_token': get_token(request),
                         'supported_context_kinds': ['patient']})


@require_GET
@ensure_csrf_cookie
def shell(request, route=''):
    # The public shell contains no patient payload. Every API checks live authority.
    manifest_path = settings.BASE_DIR / 'static' / 'comfort' / '.vite' / 'manifest.json'
    try:
        entry = json.loads(manifest_path.read_text(encoding='utf-8'))['src/main.tsx']
    except (OSError, ValueError, KeyError):
        return render(request, 'frontend_unavailable.html', status=503)
    return render(request, 'comfort.html', {'entry': entry['file'], 'styles': entry.get('css', [])})
