from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect,render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET,require_POST,require_http_methods
from . import medications,services
from .continuity_views import checked,exact
from .models import MedicationEntry,SourceVersion,CareEpisode
from .views import body
from identity.profile_views import own_workspace


@require_GET
@login_required
def my_medications(request):
    return redirect('patient_medications',workspace_id=own_workspace(request.user,'manage_medications'))


@require_GET
@login_required
@ensure_csrf_cookie
def page(request,workspace_id):
    workspace,_=services.authorize(request.user,workspace_id,'manage_medications')
    return render(request,'medications.html',{'workspace':workspace})


@require_http_methods(['GET','POST'])
@checked
def entries(request,workspace_id):
    if request.method=='POST':
        data=exact(body(request),['values','expected_revision'])
        item=medications.save(request.user,workspace_id,data['values'],data['expected_revision'])
        return JsonResponse(medications.payload(item,request.user),status=201)
    services.authorize(request.user,workspace_id,'manage_medications')
    include=request.GET.get('include_archived','0')
    if include not in ('0','1'):
        raise ValueError('Invalid filter.')
    offset=int(request.GET.get('offset',0))
    if not 0<=offset<=10000:
        raise ValueError('Invalid offset.')
    rows=MedicationEntry.objects.filter(workspace_id=workspace_id).select_related('episode','source_version')
    if include=='0':
        rows=rows.filter(status='active')
    return JsonResponse({'medications':[medications.payload(item,request.user) for item in rows.order_by('-created_at','id')[offset:offset+50]],'offset':offset,'limit':50})


@require_POST
@checked
def entry(request,workspace_id,entry_id):
    data=exact(body(request),['values','expected_revision'])
    return JsonResponse(medications.payload(medications.save(request.user,workspace_id,data['values'],data['expected_revision'],entry_id),request.user))


@require_POST
@checked
def status(request,workspace_id,entry_id):
    data=exact(body(request),['status','expected_revision'])
    return JsonResponse(medications.payload(medications.change_status(request.user,workspace_id,entry_id,data['status'],data['expected_revision']),request.user))


@require_GET
@checked
def choices(request,workspace_id):
    services.authorize(request.user,workspace_id,'manage_medications')
    services.authorize(request.user,workspace_id)
    offset=int(request.GET.get('offset',0))
    if not 0<=offset<=10000:
        raise ValueError('Invalid offset.')
    sources=SourceVersion.objects.filter(workspace_id=workspace_id).order_by('-created_at','id')
    return JsonResponse({'episodes':[{'id':e.pk,'title':e.title} for e in CareEpisode.objects.filter(workspace_id=workspace_id).order_by('-created_at')[:100]],
        'sources':[{'id':s.pk,'filename':s.original_filename,'version_number':s.version_number} for s in sources[offset:offset+100]],'offset':offset,'limit':100})
