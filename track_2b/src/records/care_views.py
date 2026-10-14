from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from . import care_services as care
from .continuity_views import checked, exact
from .views import body


def kind_or_404(kind):
    if kind not in care.KINDS:
        raise Http404
    return kind


@require_http_methods(['GET', 'POST'])
@checked
def entries(request, workspace_id, kind):
    kind_or_404(kind)
    if request.method == 'POST':
        value = exact(body(request), ['values', 'expected_revision'])
        item = care.save(request.user, workspace_id, kind, value['values'], value['expected_revision'])
        return JsonResponse(care.payload(item, kind), status=201)
    care.authorize(request.user, workspace_id)
    rows = care.KINDS[kind][1].objects.filter(workspace_id=workspace_id).order_by('-updated_at', 'id')
    return JsonResponse({'items':[care.payload(item, kind) for item in rows[:200]]})


@require_POST
@checked
def entry(request, workspace_id, kind, item_id):
    kind_or_404(kind)
    value = exact(body(request), ['values', 'expected_revision'])
    return JsonResponse(care.payload(care.save(request.user, workspace_id, kind,
        value['values'], value['expected_revision'], item_id), kind))


@require_POST
@checked
def status(request, workspace_id, kind, item_id):
    kind_or_404(kind)
    value = exact(body(request), ['status', 'expected_revision'])
    return JsonResponse(care.payload(care.change_status(request.user, workspace_id, kind,
        item_id, value['status'], value['expected_revision']), kind))


@require_GET
@checked
def history(request, workspace_id, kind, item_id):
    kind_or_404(kind)
    care.authorize(request.user, workspace_id)
    if not care.KINDS[kind][1].objects.filter(workspace_id=workspace_id, pk=item_id).exists():
        raise Http404
    return JsonResponse({'history':care.history(workspace_id, kind, item_id)})
