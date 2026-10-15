"""Version-bound PDF extraction and API work. Called inside a bounded child process."""
from io import BytesIO
import hashlib
import json
import time
from django.db import transaction
from django.http import Http404
from django.utils import timezone
import pypdf
from intelligence.trial import LOCAL_TEXT_MODEL, PARAMETERS, TrialError, available_models, configuration, redact, request_json
from .metadata import FIELDS, OUTPUT_SCHEMA, PROMPT, PROMPT_VERSION, assertion_kwargs, validate_model_output
from .models import DerivedArtifact, GenerationRun, ImageInspection, IngestionJob, MetadataAssertion, TextExtraction
from .imaging import inspect_image
from .services import audit, authorize
from .storage import StorageError, read_original


class ProcessingError(Exception):
    def __init__(self, code, state='failed'):
        self.code=code
        self.state=state


def extract(version):
    if version.media_type!='application/pdf':
        raise ProcessingError('ocr_not_available','needs_ocr')
    try:
        reader=pypdf.PdfReader(BytesIO(read_original(version)),strict=True)
        if reader.is_encrypted:
            raise ProcessingError('encrypted_pdf')
        if not 1<=len(reader.pages)<=25:
            raise ProcessingError('pdf_page_limit')
        pages=[]
        total=0
        for number,page in enumerate(reader.pages,1):
            contents=page.get_contents()
            if contents and len(contents.get_data())>20*1024*1024:
                raise ProcessingError('pdf_stream_limit')
            text=page.extract_text() or ''
            if not text.strip():
                raise ProcessingError('ocr_not_available','needs_ocr')
            total+=len(text)
            if total>100000:
                raise ProcessingError('document_text_limit')
            pages.append({'page':number,'text':text})
        return pages
    except (ProcessingError,StorageError):
        raise
    except Exception:
        raise ProcessingError('invalid_pdf') from None


def active_job(job_id, token):
    job=IngestionJob.objects.select_for_update(of=('self',)).select_related('source_version','requested_by').filter(
        pk=job_id,state='processing',lease_token=token,lease_expires_at__gt=timezone.now()).first()
    if not job:
        raise ProcessingError('job_lease_expired')
    authorize(job.requested_by,job.workspace_id,'upload_source')
    authorize(job.requested_by,job.workspace_id)
    return job


def finish_failure(job_id,token,code,state='failed'):
    with transaction.atomic():
        job=IngestionJob.objects.select_for_update().filter(pk=job_id,state='processing',lease_token=token).first()
        if not job:
            return
        job.state=state
        job.safe_error_code=code
        job.finished_at=timezone.now()
        job.save(update_fields=['state','safe_error_code','finished_at'])
        GenerationRun.objects.filter(job=job,state='processing').update(state='failed',finished_at=timezone.now())


def process_one(job_id,token,*,extract_only=False):
    run=None
    started=time.perf_counter()
    try:
        with transaction.atomic():
            job=active_job(job_id,token)
        version=job.source_version
        if version.media_type in ('image/png', 'image/jpeg', 'application/dicom'):
            inspection=ImageInspection.objects.filter(source_version=version).first()
            if not inspection:
                try:
                    details,preview,inspector=inspect_image(version)
                except StorageError:
                    raise
                except Exception:
                    raise ProcessingError('invalid_or_unsupported_image') from None
                with transaction.atomic():
                    job=active_job(job_id,token)
                    inspection,_=ImageInspection.objects.get_or_create(source_version=version,defaults={
                        'workspace_id':job.workspace_id,'details':details,'inspector_version':inspector,
                        'preview_png':preview,'preview_sha256':hashlib.sha256(preview).hexdigest() if preview else None})
            if version.content_kind=='medical_image':
                with transaction.atomic():
                    job=active_job(job_id,token)
                    job.state='manual_review'
                    job.safe_error_code=''
                    job.finished_at=timezone.now()
                    job.save(update_fields=['state','safe_error_code','finished_at'])
                    audit(job.requested_by,job.workspace,'image.manual_review',inspection)
                return 'manual_review'
        extraction=TextExtraction.objects.filter(source_version=version).first()
        if not extraction:
            pages=extract(version)
            with transaction.atomic():
                job=active_job(job_id,token)
                extraction,_=TextExtraction.objects.get_or_create(source_version=version,defaults={
                    'workspace_id':job.workspace_id,'pages':pages,'extractor_version':'pypdf-'+pypdf.__version__,
                    'text_sha256':hashlib.sha256(json.dumps(pages,sort_keys=True).encode()).hexdigest()})
        if extract_only:
            # Explicit administrative fixture preparation only. The source has
            # real extracted text, but no AI metadata has been generated.
            raise ProcessingError('text_extracted_manual_metadata','manual_review')
        try:
            config=configuration()
        except TrialError:
            raise ProcessingError('model_configuration_pending','waiting_model') from None
        output_format={'response_format':{'type':'json_schema','json_schema':{
            'name':'record_metadata','strict':True,'schema':OUTPUT_SCHEMA}}} if config['model']==LOCAL_TEXT_MODEL else {}
        with transaction.atomic():
            job=active_job(job_id,token)
            run=GenerationRun.objects.create(workspace_id=job.workspace_id,job=job,source_version=version,
                model_name=config['model'],prompt_version=PROMPT_VERSION,configuration={
                    'base_url':config['base'],'model_identity':config.get('identity',{}),'request_timeout_seconds':config.get('request_timeout',90),'parameters':{**PARAMETERS,'max_tokens':1024,**output_format},
                    'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
                    'source_sha256':version.sha256,'text_sha256':extraction.text_sha256})
        available_models(config)
        response=request_json(config,'chat/completions',{'model':config['model'],**PARAMETERS,'max_tokens':1024,**output_format,
            'messages':[{'role':'system','content':PROMPT},{'role':'user','content':'Untrusted source pages:\n'+json.dumps(extraction.pages)}]})
        try:
            choice=response['choices'][0]
            if choice.get('finish_reason')!='stop':
                raise ValueError('Incomplete generation.')
            payload=validate_model_output(json.loads(choice['message']['content']),extraction.pages)
        except (ValueError,TypeError,KeyError,IndexError):
            raise ProcessingError('invalid_model_output') from None
        with transaction.atomic():
            job=active_job(job_id,token)
            artifact=DerivedArtifact.objects.create(workspace_id=job.workspace_id,source_version=version,
                extraction=extraction,generation=run,payload=redact(payload,config['key']))
            for field in FIELDS:
                MetadataAssertion.objects.create(workspace_id=job.workspace_id,source_version=version,
                    field_name=field,origin='ai',review_state='proposed',evidence_artifact=artifact,
                    locator=payload['evidence'][field] or {},**assertion_kwargs(field,payload[field]))
            run.state='completed'
            run.finished_at=timezone.now()
            run.latency_seconds=time.perf_counter()-started
            usage=response.get('usage',{})
            run.usage={key:value for key,value in usage.items() if key in ('prompt_tokens','completion_tokens','total_tokens') and type(value) is int and value>=0} if isinstance(usage,dict) else {}
            run.save(update_fields=['state','finished_at','latency_seconds','usage'])
            job.state='review_ready'
            job.safe_error_code=''
            job.finished_at=timezone.now()
            job.save(update_fields=['state','safe_error_code','finished_at'])
            audit(job.requested_by,job.workspace,'ingestion.review_ready',artifact)
        return 'review_ready'
    except ProcessingError as error:
        finish_failure(job_id,token,error.code,error.state)
        return error.state
    except Http404:
        finish_failure(job_id,token,'authority_unavailable')
    except TrialError:
        finish_failure(job_id,token,'model_access_failed')
    except StorageError:
        finish_failure(job_id,token,'source_integrity_or_storage')
    except Exception:
        # Never print a parser/provider/database exception with source text or keys.
        finish_failure(job_id,token,'processing_failed')
    return 'failed'
