"""A patient-reported medication entry for one visit/context, never a dose engine."""
import uuid
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from identity.authorization import can_access_workspace
from identity.profile_services import revision, text
from . import services
from .metadata import validate_values
from .models import CareEpisode, MedicationEntry, SourceVersion

LIMITS={'medicine_name':160,'dose':120,'frequency':120,'route':64,'instructions':500}
USE_STATES=('reported_taken','reported_prescribed','not_taken','unknown')


def values(item):
    return {**{key:getattr(item,key) for key in LIMITS},'use_status':item.use_status,
        'visit_date':{'precision':item.date_precision,'year':item.value_year,'month':item.value_month,'day':item.value_day},
        'episode_id':item.episode_id,'source_version_id':item.source_version_id}


def payload(item,user):
    readable=can_access_workspace(user,item.workspace_id)
    return {'id':item.pk,'revision':item.revision,'status':item.status,'values':values(item),
        'episode_title':item.episode.title if item.episode_id else None,
        'source_filename':item.source_version.original_filename if readable and item.source_version_id else None,
        'source_download_url':f'/api/workspaces/{item.workspace_id}/versions/{item.source_version_id}/original/' if readable and item.source_version_id else None,
        'verification':'Patient-reported; not a verified prescription or treatment recommendation.',
        'created_at':item.created_at,'updated_at':item.updated_at}


def linked(model,value,workspace):
    if value is None:
        return None
    item=model.objects.filter(pk=uuid.UUID(str(value)),workspace=workspace).first()
    if not item:
        raise Http404
    return item


def save(user,workspace_id,data,expected_revision,entry_id=None):
    revision(expected_revision)
    if not isinstance(data,dict) or set(data)!=set(LIMITS)|{'use_status','visit_date','episode_id','source_version_id'}:
        raise ValueError('Unexpected medication fields.')
    cleaned={key:text(data[key],limit,key=='medicine_name') for key,limit in LIMITS.items()}
    if data['use_status'] not in USE_STATES:
        raise ValueError('Choose whether this medicine was prescribed or taken.')
    parts=data['visit_date']
    validate_values({'document_type':'other','document_date':parts,'facility_name':None})
    cleaned.update(use_status=data['use_status'],date_precision=parts['precision'],value_year=parts['year'],value_month=parts['month'],value_day=parts['day'])
    with transaction.atomic():
        workspace,_=services.authorize(user,workspace_id,'manage_medications',lock=True)
        item=MedicationEntry.objects.select_for_update().filter(pk=entry_id,workspace=workspace).first() if entry_id else None
        if entry_id and item is None:
            raise Http404
        if expected_revision!=(item.revision if item else 0):
            raise services.Conflict('Medication entry changed. Reload before saving.')
        cleaned['episode']=linked(CareEpisode,data['episode_id'],workspace)
        if data['source_version_id'] is not None:
            services.authorize(user,workspace_id,lock=True)
        cleaned['source_version']=linked(SourceVersion,data['source_version_id'],workspace)
        if item is None:
            item=MedicationEntry.objects.create(workspace=workspace,created_by=user,updated_by=user,**cleaned)
        else:
            if item.status!='active':
                raise services.Conflict('Restore this entry before editing it.')
            for key,value in cleaned.items():
                setattr(item,key,value)
            item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=[*cleaned,'revision','updated_by','updated_at'])
        services.audit(user,workspace,'medication.save',item)
        return item


def change_status(user,workspace_id,entry_id,status,expected_revision):
    revision(expected_revision)
    if status not in ('active','archived'):
        raise ValueError('Choose active or archived.')
    with transaction.atomic():
        workspace,_=services.authorize(user,workspace_id,'manage_medications',lock=True)
        item=MedicationEntry.objects.select_for_update().filter(pk=entry_id,workspace=workspace).first()
        if not item:
            raise Http404
        if item.revision!=expected_revision:
            raise services.Conflict('Medication entry changed. Reload before saving.')
        if item.status!=status:
            item.status=status; item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=['status','revision','updated_by','updated_at'])
            services.audit(user,workspace,'medication.'+status,item)
        return item
