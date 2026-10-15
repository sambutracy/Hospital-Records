from functools import wraps
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from . import journal
from .continuity_views import checked, exact
from .views import body
from .models import JournalEvent, JournalDraft


def journal_checked(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        try: return view(*args,**kwargs)
        except journal.InvalidTime as error: return JsonResponse({'error':error.code},status=400)
    return checked(wrapped)


@require_http_methods(['GET','POST'])
@journal_checked
def entries(request,workspace_id):
    if request.method=='GET':
        journal.authorize(request.user,workspace_id)
        return JsonResponse(journal.listing(workspace_id,request.GET))
    value=exact(body(request),['values','expected_revision','draft_revision'])
    return JsonResponse(journal.payload(journal.save(request.user,workspace_id,value['values'],
        value['expected_revision'],draft_revision=value['draft_revision'])),status=201)


@require_http_methods(['GET','POST'])
@journal_checked
def entry(request,workspace_id,event_id):
    if request.method=='POST':
        value=exact(body(request),['values','expected_revision','draft_revision'])
        return JsonResponse(journal.payload(journal.save(request.user,workspace_id,value['values'],
            value['expected_revision'],event_id,value['draft_revision'])))
    journal.authorize(request.user,workspace_id)
    item=JournalEvent.objects.filter(workspace_id=workspace_id,pk=event_id).first()
    if item is None: raise Http404
    return JsonResponse(journal.payload(item))


@require_POST
@journal_checked
def status(request,workspace_id,event_id):
    value=exact(body(request),['status','expected_revision'])
    return JsonResponse(journal.payload(journal.change_status(request.user,workspace_id,event_id,
        value['status'],value['expected_revision'])))


@require_GET
@journal_checked
def history(request,workspace_id,event_id):
    journal.authorize(request.user,workspace_id)
    item=JournalEvent.objects.filter(workspace_id=workspace_id,pk=event_id).first()
    if item is None: raise Http404
    return JsonResponse({'contract_version':1,'history':[{'revision':row.revision,'recorded_at':row.created_at,
        'actor_id':row.actor_id,'snapshot':row.snapshot} for row in item.history.order_by('-revision')[:100]],
        'truncated':item.revision>100})


@require_http_methods(['GET','POST'])
@journal_checked
def draft(request,workspace_id):
    if request.method=='POST':
        value=exact(body(request),['fields','expected_revision','event_id','base_revision'])
        return JsonResponse(journal.draft_payload(journal.save_draft(request.user,workspace_id,**value)))
    journal.authorize(request.user,workspace_id)
    return JsonResponse(journal.draft_payload(JournalDraft.objects.filter(workspace_id=workspace_id).first()))


@require_POST
@journal_checked
def discard(request,workspace_id):
    value=exact(body(request),['expected_revision'])
    journal.discard_draft(request.user,workspace_id,value['expected_revision'])
    return JsonResponse({'discarded':True})
