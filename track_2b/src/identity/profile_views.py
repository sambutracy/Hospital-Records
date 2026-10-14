from django.contrib.auth.decorators import login_required
from django.http import Http404,JsonResponse
from django.shortcuts import redirect,render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from records import services
from records.continuity import recipient
from records.continuity_views import checked, exact
from records.views import body
from . import profile_services as profiles
from .models import CareCircleEntry,PatientWorkspace
from .authorization import effective_capabilities


def own_workspace(user,action):
    ids=list(PatientWorkspace.objects.filter(pk__in=effective_capabilities(user,action).values('workspace_id')).values_list('pk',flat=True)[:2])
    if len(ids)!=1:
        raise Http404
    return ids[0]


@require_GET
@login_required
def my_profile(request):
    return redirect('patient_profile',workspace_id=own_workspace(request.user,'manage_profile'))


@require_GET
@login_required
@ensure_csrf_cookie
def profile_page(request,workspace_id):
    workspace,_=services.authorize(request.user,workspace_id,'manage_profile')
    return render(request,'patient_profile.html',{'workspace':workspace})


@require_http_methods(['GET','POST'])
@checked
def profile(request,workspace_id):
    if request.method=='POST':
        value=exact(body(request),['values','expected_revision'])
        profiles.save_profile(request.user,workspace_id,value['values'],value['expected_revision'])
    workspace,_=services.authorize(request.user,workspace_id,'manage_profile')
    return JsonResponse(profiles.profile_payload(workspace))


@require_http_methods(['GET','POST'])
@checked
def contacts(request,workspace_id):
    if request.method=='POST':
        value=exact(body(request),['values','expected_revision'])
        item=profiles.save_contact(request.user,workspace_id,value['values'],value['expected_revision'])
        return JsonResponse(profiles.contact_payload(item),status=201)
    services.authorize(request.user,workspace_id,'manage_profile')
    include=request.GET.get('include_archived','0')
    if include not in ('0','1'):
        raise ValueError('Invalid filter.')
    rows=CareCircleEntry.objects.filter(workspace_id=workspace_id).select_related('recipient_user__person')
    if include=='0':
        rows=rows.filter(status='active')
    return JsonResponse({'contacts':[profiles.contact_payload(c) for c in rows.order_by('-is_next_of_kin','-is_emergency_contact','full_name','id')[:200]]})


@require_POST
@checked
def contact(request,workspace_id,contact_id):
    value=exact(body(request),['values','expected_revision'])
    item=profiles.save_contact(request.user,workspace_id,value['values'],value['expected_revision'],contact_id)
    return JsonResponse(profiles.contact_payload(item))


@require_POST
@checked
def contact_state(request,workspace_id,contact_id):
    value=exact(body(request),['status','expected_revision'])
    return JsonResponse(profiles.contact_payload(profiles.contact_status(request.user,workspace_id,contact_id,value['status'],value['expected_revision'])))


@require_POST
@checked
def resolve_contact(request,workspace_id):
    services.authorize(request.user,workspace_id,'manage_profile')
    value=exact(body(request),['recipient_id'])
    target=recipient(value['recipient_id'],request.user)
    return JsonResponse({'id':target.pk,'name':target.person.display_name})


@require_GET
@checked
def circle_choices(request,workspace_id):
    services.authorize(request.user,workspace_id,'manage_profile')
    rows=CareCircleEntry.objects.filter(workspace_id=workspace_id,status='active',recipient_user__is_active=True,
        recipient_user__person__status='active').select_related('recipient_user__person').order_by('full_name','id')
    return JsonResponse({'contacts':[{'id':c.pk,'name':c.full_name,'relationship':c.relationship,
        'recipient_id':c.recipient_user_id,'account_name':c.recipient_user.person.display_name} for c in rows[:100]]})
