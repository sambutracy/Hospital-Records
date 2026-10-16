import uuid
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from . import care_intelligence as ai, care_services
from .models import AssistantTask
from .views import api, body


@require_GET
@api
def status(request,workspace_id):
    from django.conf import settings
    care_services.authorize(request.user,workspace_id)
    return JsonResponse({'enabled':settings.CARE_INTELLIGENCE_ENABLED,'selection_limit':ai.MAX_SELECTION})


@require_GET
@api
def candidates(request,workspace_id):
    return JsonResponse(ai.candidates(request.user,workspace_id,request.GET))


@require_http_methods(['GET','POST'])
@api
def tasks(request,workspace_id):
    if request.method=='POST':
        return JsonResponse(ai.payload(ai.create(request.user,workspace_id,body(request))),status=202)
    ai.enabled(); care_services.authorize(request.user,workspace_id)
    if set(request.GET)-{'kind','packet_id'}: raise ValueError('Unexpected task filter.')
    kind=request.GET.get('kind')
    if kind not in ai.KINDS: raise ValueError('Choose a task type.')
    rows=AssistantTask.objects.filter(workspace_id=workspace_id,requested_by=request.user,kind=kind)
    if request.GET.get('packet_id'): rows=rows.filter(packet_revision__packet_id=uuid.UUID(request.GET['packet_id']))
    items=[]
    for task in rows.order_by('-created_at')[:10]:
        try: ai.get(request.user,workspace_id,task.pk)
        except Http404: continue
        items.append(ai.payload(task))
    return JsonResponse({'tasks':items})


@require_GET
@api
def task(request,workspace_id,task_id):
    item=ai.get(request.user,workspace_id,task_id)
    ai.services.audit(request.user,item.workspace,'care_ai.result_read',item)
    return JsonResponse(ai.payload(item))


@require_POST
@api
def review(request,workspace_id,task_id):
    value=body(request)
    if not isinstance(value,dict) or 'outcome' not in value or set(value)-{'outcome','texts'}:
        raise ValueError('Unexpected review fields.')
    return JsonResponse(ai.review(request.user,workspace_id,task_id,value['outcome'],value.get('texts')))
