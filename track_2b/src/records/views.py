from functools import wraps
from io import BytesIO
import hashlib
import json
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from . import services
from . import assistant
from . import facility_search
from .facilities import selection_token
from .metadata import FIELDS, assertion_value
from .models import AssistantTask, ConsultationPacket, ImageInspection, IngestionJob, SourceRecord, SourceVersion
from .storage import StorageError, read_original


def api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error':'sign_in_required'},status=401)
        try:
            return view(request,*args,**kwargs)
        except Http404:
            return JsonResponse({'error':'resource_unavailable'},status=404)
        except services.Conflict as error:
            return JsonResponse({'error':str(error)},status=409)
        except StorageError:
            return JsonResponse({'error':'original_storage_unavailable'},status=503)
        except (ValueError, TypeError, KeyError):
            return JsonResponse({'error':'invalid_request'},status=400)
    return wrapped


def body(request):
    if request.content_type != 'application/json':
        raise ValueError('Use JSON.')
    value=json.loads(request.body)
    if not isinstance(value,dict):
        raise ValueError('Use a JSON object.')
    return value


def version_payload(version):
    return {'id':version.pk,'record_id':version.record_id,'version_number':version.version_number,
            'original_filename':version.original_filename,'media_type':version.media_type,
            'byte_size':version.byte_size,'sha256':version.sha256,'uploaded_at':version.created_at,
            'supersedes_id':version.supersedes_id,'content_kind':version.content_kind,
            'image_details_url':f'/api/workspaces/{version.workspace_id}/versions/{version.pk}/image/' if version.media_type in ('image/jpeg','image/png','application/dicom') else None,
            'download_url':f'/api/workspaces/{version.workspace_id}/versions/{version.pk}/original/'}


def job_payload(job):
    return {'id':job.pk,'source_version_id':job.source_version_id,'attempt_number':job.attempt_number,
            'state':job.state,'error_code':job.safe_error_code,'started_at':job.started_at,'finished_at':job.finished_at}


def record_payload(record, details=False):
    version=record.current_version
    head=version.metadata_head
    result={'id':record.pk,'current_version':version_payload(version),'metadata':services.head_payload(head)}
    result['jobs']=[job_payload(job) for job in version.jobs.order_by('-attempt_number')]
    if details:
        result['versions']=[version_payload(item) for item in record.versions.order_by('-version_number')]
        result['proposals']=[{'id':artifact.pk,'values':artifact.payload,'model':artifact.generation.model_name,
                             'prompt_version':artifact.generation.prompt_version}
                            for artifact in version.derivedartifact_set.select_related('generation').order_by('-created_at')]
        result['metadata_history']=[{'id':item.pk,'field':item.field_name,'value':assertion_value(item),
            'facility_maps_url':item.facility_maps_url,
            'facility_location':item.facility_location,
            'origin':item.origin,'review_state':item.review_state,'supersedes_id':item.supersedes_id,
            'evidence_artifact_id':item.evidence_artifact_id,'locator':item.locator,'created_at':item.created_at}
            for item in version.assertions.order_by('created_at','id')]
    return result


def upload(request, workspace_id, record_id=None):
    services.authorize(request.user,workspace_id,'upload_source')
    files=request.FILES
    if getattr(request,'upload_too_large',False) or set(files)!={'file'} or len(files.getlist('file'))!=1:
        return JsonResponse({'error':'Upload exactly one PDF, JPEG, PNG or Part 10 DICOM up to 10 MB.'},status=400)
    if set(request.POST)-{'content_kind'} or len(request.POST.getlist('content_kind'))>1:
        raise ValueError('Unexpected upload fields.')
    version,created=services.ingest(request.user,workspace_id,files['file'],record_id,request.POST.get('content_kind','document'))
    return JsonResponse({'version':version_payload(version),'created':created},status=201 if created else 200)


@ensure_csrf_cookie
@require_http_methods(['GET','POST'])
@api
def records(request,workspace_id):
    if request.method=='POST':
        return upload(request,workspace_id)
    return records_listing(request,workspace_id,request.GET)


@require_POST
@api
def records_search(request,workspace_id):
    """Private search terms travel in JSON, never navigation URLs or browser storage."""
    values=body(request)
    if set(values)-{'q','offset','order','document_type','reviewed','uploaded_from','uploaded_until','document_year'}:
        raise ValueError('Unexpected filters.')
    return records_listing(request,workspace_id,values)


def records_listing(request,workspace_id,filters):
    services.authorize(request.user,workspace_id)
    query=filters.get('q','').strip()
    if len(query)>160:
        raise ValueError('Query too long.')
    offset=int(filters.get('offset',0))
    if not 0<=offset<=10000:
        raise ValueError('Invalid offset.')
    rows=SourceRecord.objects.filter(workspace_id=workspace_id,current_version__isnull=False)
    episode_id=filters.get('episode')
    if episode_id:
        import uuid
        from .models import CareEpisode
        episode=CareEpisode.objects.filter(workspace_id=workspace_id,pk=uuid.UUID(episode_id)).first()
        if not episode:
            raise Http404
        rows=rows.filter(current_version__episodesource__episode=episode).distinct()
    if query:
        rows=rows.filter(Q(current_version__original_filename__icontains=query)
            | Q(current_version__metadata_head__facility_name__value_text__icontains=query)
            | Q(current_version__metadata_head__document_type__value_text__icontains=query)
            | Q(current_version__extraction__pages__icontains=query))
    from .metadata import TYPES
    kind=filters.get('document_type','')
    if kind:
        if kind not in TYPES: raise ValueError('Invalid type.')
        rows=rows.filter(current_version__metadata_head__document_type__value_text=kind)
    reviewed=filters.get('reviewed','')
    if reviewed not in ('','yes','no'): raise ValueError('Invalid review status.')
    if reviewed=='yes': rows=rows.filter(current_version__metadata_head__revision__gt=0)
    if reviewed=='no': rows=rows.filter(current_version__metadata_head__revision=0)
    year=filters.get('document_year','')
    if year:
        year=int(year)
        if not 1<=year<=9999: raise ValueError('Invalid year.')
        rows=rows.filter(current_version__metadata_head__document_date__value_year=year)
    from datetime import date,datetime,time,timedelta,timezone
    for key,lookup in [('uploaded_from','current_version__created_at__gte'),('uploaded_until','current_version__created_at__lt')]:
        value=filters.get(key,'')
        if value:
            boundary=date.fromisoformat(value)
            if key=='uploaded_until': boundary+=timedelta(days=1)
            rows=rows.filter(**{lookup:datetime.combine(boundary,time.min,tzinfo=timezone.utc)})
    order=filters.get('order','upload')
    if order not in ('upload','document_date'):
        raise ValueError('Choose upload or document_date order.')
    rows=rows.select_related('current_version__metadata_head__document_type','current_version__metadata_head__document_date','current_version__metadata_head__facility_name')
    if order=='document_date':
        from django.db.models import F
        rows=rows.order_by(F('current_version__metadata_head__document_date__value_year').desc(nulls_last=True),
            F('current_version__metadata_head__document_date__value_month').desc(nulls_last=True),
            F('current_version__metadata_head__document_date__value_day').desc(nulls_last=True),'-created_at','id')
    else:
        rows=rows.order_by('-created_at','id')
    total=rows.count()
    return JsonResponse({'records':[record_payload(record) for record in rows[offset:offset+50]],'offset':offset,'limit':50,
        'total':total,'has_more':offset+50<total,
        'order':'known document-date components, newest first; partial dates are not precise care-event times; unknown dates last' if order=='document_date' else 'upload time, not inferred clinical date'})


@require_GET
@api
def record(request,workspace_id,record_id):
    services.authorize(request.user,workspace_id)
    item=SourceRecord.objects.filter(workspace_id=workspace_id,pk=record_id).first()
    if not item:
        raise Http404
    return JsonResponse(record_payload(item,True))


@require_POST
@api
def new_version(request,workspace_id,record_id):
    return upload(request,workspace_id,record_id)


@require_GET
@api
def original(request,workspace_id,version_id):
    workspace,_=services.authorize(request.user,workspace_id)
    version=SourceVersion.objects.filter(workspace=workspace,pk=version_id).first()
    if not version:
        raise Http404
    data=read_original(version)
    services.audit(request.user,workspace,'source.download',version)
    return FileResponse(BytesIO(data),as_attachment=True,filename=version.original_filename,content_type=version.media_type)


@require_GET
@api
def image_details(request,workspace_id,version_id):
    services.authorize(request.user,workspace_id)
    version=SourceVersion.objects.filter(workspace_id=workspace_id,pk=version_id,media_type__in=['image/jpeg','image/png','application/dicom']).first()
    if not version:
        raise Http404
    inspection=ImageInspection.objects.filter(workspace_id=workspace_id,source_version=version).first()
    if not inspection:
        job=version.jobs.order_by('-attempt_number').first()
        return JsonResponse({'state':job.state,'error_code':job.safe_error_code,'inspection':None},status=202)
    services.audit(request.user,version.workspace,'image.inspect_read',inspection)
    return JsonResponse({'source_version_id':version.pk,'source_sha256':version.sha256,
        'content_kind':version.content_kind,'inspector_version':inspection.inspector_version,
        'details':inspection.details,'metadata_verification':'technical source facts, not patient-confirmed or clinician-verified',
        'preview_url':f'/api/workspaces/{workspace_id}/versions/{version.pk}/preview/' if inspection.preview_png is not None else None,
        'preview_sha256':inspection.preview_sha256})


@require_GET
@api
def image_preview(request,workspace_id,version_id):
    workspace,_=services.authorize(request.user,workspace_id)
    inspection=ImageInspection.objects.select_related('source_version').filter(workspace=workspace,source_version_id=version_id).first()
    if not inspection:
        raise Http404
    if inspection.preview_png is None:
        return JsonResponse({'error':'external_dicom_viewer_required','original_download_available':True},status=409)
    data=bytes(inspection.preview_png)
    if hashlib.sha256(data).hexdigest()!=inspection.preview_sha256:
        raise StorageError('Preview integrity failed.')
    services.audit(request.user,workspace,'image.preview_read',inspection)
    response=FileResponse(BytesIO(data),content_type='image/png')
    response['Content-Disposition']='inline; filename="record-preview.png"'
    response['X-Comfort-Preview']='non-diagnostic'
    return response


@require_POST
@api
def review(request,workspace_id,record_id):
    values=body(request)
    if set(values)-{'values','expected_revision','source_version_id','proposal_id','facility_maps_url','facility_selection'}:
        raise ValueError('Unexpected fields.')
    head=services.review(request.user,workspace_id,record_id,values['values'],values['expected_revision'],values['source_version_id'],values.get('proposal_id'),values.get('facility_maps_url',services.UNSET_LOCATION),values.get('facility_selection',services.UNSET_LOCATION))
    return JsonResponse(services.head_payload(head))


@require_POST
@api
def retry(request,workspace_id,job_id):
    return JsonResponse(job_payload(services.retry_job(request.user,workspace_id,job_id)),status=201)


def packet_payload(packet):
    revision=packet.revisions.get(state='approved')
    return {'id':packet.pk,'purpose':packet.purpose,'revision_id':revision.pk,'approved_at':revision.approved_at,
        'items':[{'source_version':version_payload(item.source_version),
                  'facility_maps_url':item.facility_name.facility_maps_url if item.facility_name else None,
                  'facility_location':item.facility_name.facility_location if item.facility_name else None,
                  'metadata':{field:assertion_value(getattr(item,field)) for field in FIELDS},
                  'assertion_ids':{field:getattr(item,field+'_id') for field in FIELDS}}
                 for item in revision.items.select_related('source_version',*FIELDS).order_by('created_at','id')],
        'access':'private patient packet; not a clinician share grant'}


@require_http_methods(['GET','POST'])
@api
def packets(request,workspace_id):
    if request.method=='POST':
        values=body(request)
        if set(values)!={'purpose','source_version_ids'}:
            raise ValueError('Unexpected packet fields.')
        packet=services.create_packet(request.user,workspace_id,values['purpose'],values['source_version_ids'])
        return JsonResponse(packet_payload(packet),status=201)
    services.authorize(request.user,workspace_id)
    return JsonResponse({'packets':[{'id':p.pk,'purpose':p.purpose,'created_at':p.created_at} for p in ConsultationPacket.objects.filter(workspace_id=workspace_id).order_by('-created_at')[:50]]})


@require_GET
@api
def packet(request,workspace_id,packet_id):
    services.authorize(request.user,workspace_id)
    item=ConsultationPacket.objects.filter(workspace_id=workspace_id,pk=packet_id).first()
    if not item:
        raise Http404
    return JsonResponse(packet_payload(item))


def assistant_payload(task):
    sources=list(task.sources.select_related('source_version__record','source_version__metadata_head').order_by('source_label'))
    return {'id':task.pk,'kind':task.kind,'state':task.state,'error_code':task.safe_error_code,
        'query':task.parameters.get('query') if task.kind=='search' else None,
        'packet_id':task.packet_revision.packet_id if task.packet_revision_id else None,
        'created_at':task.created_at,'started_at':task.started_at,'finished_at':task.finished_at,'model':task.model_name or None,
        'prompt_version':task.prompt_version or None,'coverage':task.coverage,
        'configuration':task.configuration,'latency_seconds':task.latency_seconds,'usage':task.usage,
        'result':task.result,
        'sources':[{'source_version_id':s.source_version_id,'record_id':s.source_version.record_id,
            'original_filename':s.source_version.original_filename,'source_sha256':s.source_version.sha256,
            'current_version':s.source_version.record.current_version_id==s.source_version_id,
            'metadata_changed_since_request':s.source_version.metadata_head.revision!=s.metadata_revision} for s in sources],
        'verification':'AI suggestions need review; citations are checked structurally, not for clinical correctness'}


@require_http_methods(['GET','POST'])
@api
def assistant_tasks(request,workspace_id):
    if request.method=='POST':
        values=body(request)
        if set(values)!={'kind','parameters'}:
            raise ValueError('Unexpected assistant fields.')
        try:
            task=assistant.create_task(request.user,workspace_id,values['kind'],values['parameters'])
        except ValueError as error:
            return JsonResponse({'error':str(error)},status=400)
        return JsonResponse(assistant_payload(task),status=202)
    services.authorize(request.user,workspace_id)
    tasks=AssistantTask.objects.filter(workspace_id=workspace_id,requested_by=request.user).filter(kind__in=['search','packet_overview','explain_term']).order_by('-created_at')[:10]
    # A prepare permission can be revoked independently; omit those task details.
    visible=[]
    for task in tasks:
        try:
            assistant.authority(request.user,workspace_id,task.kind)
        except Http404:
            continue
        visible.append(assistant_payload(task))
    return JsonResponse({'tasks':visible})


@require_GET
@api
def assistant_task(request,workspace_id,task_id):
    task=assistant.get_task(request.user,workspace_id,task_id)
    if task.kind not in ('search','packet_overview','explain_term'):
        raise Http404
    services.audit(request.user,task.workspace,'assistant.result_read',task)
    return JsonResponse(assistant_payload(task))


@require_POST
@api
def assistant_cancel(request,workspace_id,task_id):
    task=assistant.get_task(request.user,workspace_id,task_id)
    if task.kind not in ('search','packet_overview','explain_term'):
        raise Http404
    return JsonResponse(assistant_payload(assistant.cancel_task(request.user,workspace_id,task_id)))


@require_GET
@api
def assistant_status(request,workspace_id):
    services.authorize(request.user,workspace_id)
    from django.conf import settings
    from intelligence.trial import configuration, TrialError
    from .worker_health import status as worker_status
    try:
        config=configuration()
    except TrialError:
        return JsonResponse({'configured':False,'model':None,'worker':worker_status(),'facility_search_enabled':bool(settings.FACILITY_SEARCH_URL)})
    return JsonResponse({'configured':True,'model':config['model'],'worker':worker_status(),
        'facility_search_enabled':bool(settings.FACILITY_SEARCH_URL),
        'text_only':config.get('identity',{}).get('modalities')==['text'],
        'community_derivative':config.get('identity',{}).get('community_derivative',False),
        'note':'configuration present; availability is checked when processing a request'})


@require_POST
@api
def facilities(request,workspace_id):
    services.authorize(request.user,workspace_id,'review_metadata')
    services.authorize(request.user,workspace_id)
    values=body(request)
    if set(values)!={'query'}:
        raise ValueError('Unexpected search fields.')
    from django.conf import settings
    if not settings.FACILITY_SEARCH_URL:
        return JsonResponse({'error':'Hospital lookup is unavailable here. Enter the issuing facility name directly.'},status=503)
    try:
        results=facility_search.search(values['query'])
    except facility_search.SearchBusy:
        return JsonResponse({'error':'Please wait a moment before another hospital search.'},status=429)
    except facility_search.SearchUnavailable:
        return JsonResponse({'error':'Hospital search is unavailable. Try again later; your record is unchanged.'},status=503)
    # Recheck authority after an external request before rendering selected-place tokens.
    services.authorize(request.user,workspace_id,'review_metadata')
    services.authorize(request.user,workspace_id)
    return JsonResponse({'results':[{**item,'selection_token':selection_token(item,request.user,workspace_id)} for item in results],
        'attribution':facility_search.ATTRIBUTION})
