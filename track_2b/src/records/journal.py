"""Private patient observations and bounded editor recovery. No disclosure side effects."""
from datetime import date, datetime, time, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.http import Http404
from django.utils import timezone
from identity.profile_services import revision, text
from . import services
from .care_services import authorize, care_date
from .models import JournalEvent, JournalDraft, PatientHealthConcern

FIELDS = {'category','description','occurrence','time','timezone','fold','severity','concern_id'}
DRAFT_FIELDS = {'category':16,'description':2000,'precision':8,'year':4,'month':2,'day':2,
    'time':5,'timezone':64,'fold':1,'severity':2,'concern_id':36}


class InvalidTime(ValueError):
    def __init__(self, code): self.code = code


def clean(values):
    if not isinstance(values, dict) or set(values) != FIELDS:
        raise ValueError('Unexpected journal fields.')
    category = values['category']
    if category not in ('note','symptom'): raise ValueError('Unsupported category.')
    occurrence = care_date(values['occurrence'])
    zone = text(values['timezone'],64,True)
    try: tz = ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError): raise InvalidTime('journal_invalid_timezone') from None
    severity = values['severity']
    if severity is not None and (type(severity) is not int or category != 'symptom' or not 0 <= severity <= 10):
        raise ValueError('Severity is optional and from zero to ten for symptoms.')
    local_time, instant, fold = None, None, values['fold']
    if fold is not None and (type(fold) is not int or fold not in (0,1)): raise ValueError('Invalid fold.')
    if values['time'] is not None:
        value = values['time']
        if not isinstance(value,str) or len(value)!=5 or value[2]!=':': raise InvalidTime('journal_invalid_time')
        try: local_time = time.fromisoformat(value)
        except ValueError: raise InvalidTime('journal_invalid_time') from None
        if occurrence['precision']!='day': raise InvalidTime('journal_time_needs_day')
        naive = datetime(occurrence['year'],occurrence['month'],occurrence['day'],local_time.hour,local_time.minute)
        candidates = [naive.replace(tzinfo=tz,fold=f).astimezone(dt_timezone.utc) for f in (0,1)]
        valid = [candidate.astimezone(tz).replace(tzinfo=None)==naive for candidate in candidates]
        if not any(valid): raise InvalidTime('journal_nonexistent_time')
        if all(valid) and candidates[0]!=candidates[1] and fold is None:
            raise InvalidTime('journal_ambiguous_time')
        fold = fold if fold is not None else 0
        if not valid[fold]: raise InvalidTime('journal_invalid_time')
        instant = candidates[fold]
    elif fold is not None: raise ValueError('Fold needs a time.')
    return {'category':category,'description':text(values['description'],2000,True),
        'occurrence':occurrence,'occurrence_time':local_time,'timezone_name':zone,
        'occurred_at':instant,'time_fold':fold,'severity':severity,'concern_id':values['concern_id']}


def concern(workspace, key, old_key=None):
    if key is None: return None
    if not isinstance(key,str): raise ValueError('Invalid concern.')
    try: linked = PatientHealthConcern.objects.filter(pk=key,workspace=workspace).first()
    except (ValueError,ValidationError): raise ValueError('Invalid concern.') from None
    if linked is None: raise Http404
    if linked.status!='active' and str(linked.pk)!=str(old_key):
        raise services.Conflict('Restore this concern before linking it.')
    return linked.pk


def payload(item):
    return {'contract_version':1,'id':item.pk,'revision':item.revision,'status':item.status,
        'created_at':item.created_at,'updated_at':item.updated_at,'created_by_id':item.created_by_id,
        'updated_by_id':item.updated_by_id,'provenance':'patient_reported','visibility':'private',
        'values':{'category':item.category,'description':item.description,'occurrence':item.occurrence,
            'time':item.occurrence_time.strftime('%H:%M') if item.occurrence_time else None,
            'timezone':item.timezone_name,'fold':item.time_fold,'severity':item.severity,
            'concern_id':item.concern_id},'occurred_at':item.occurred_at}


def save(user, workspace_id, values, expected_revision, event_id=None, draft_revision=None):
    revision(expected_revision)
    if draft_revision is not None: revision(draft_revision)
    cleaned = clean(values)
    with transaction.atomic():
        workspace = authorize(user,workspace_id,lock=True)
        item = JournalEvent.objects.select_for_update().filter(pk=event_id,workspace=workspace).first() if event_id else None
        if event_id and item is None: raise Http404
        if expected_revision!=(item.revision if item else 0): raise services.Conflict('Journal entry changed.')
        if item and item.status!='active': raise services.Conflict('Restore this entry before editing.')
        cleaned['concern_id'] = concern(workspace,cleaned['concern_id'],item.concern_id if item else None)
        draft = None
        if draft_revision is not None:
            draft = JournalDraft.objects.select_for_update().filter(workspace=workspace).first()
            if not draft or draft.revision!=draft_revision or draft.event_id!=(item.pk if item else None) or draft.base_revision!=expected_revision:
                raise services.Conflict('Recovery draft changed. Your entry was not published.')
        if item:
            for key,value in cleaned.items(): setattr(item,key,value)
            item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=[*cleaned,'revision','updated_by','updated_at'])
        else:
            item = JournalEvent.objects.create(workspace=workspace,created_by=user,updated_by=user,**cleaned)
        if draft: draft.delete()
        services.audit(user,workspace,'journal.save',item)
        return item


def change_status(user, workspace_id, event_id, status, expected_revision):
    revision(expected_revision)
    if status not in ('active','archived'): raise ValueError('Invalid state.')
    with transaction.atomic():
        workspace = authorize(user,workspace_id,lock=True)
        item = JournalEvent.objects.select_for_update().filter(pk=event_id,workspace=workspace).first()
        if item is None: raise Http404
        if item.revision!=expected_revision: raise services.Conflict('Journal entry changed.')
        if item.status!=status:
            item.status=status; item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=['status','revision','updated_by','updated_at'])
            services.audit(user,workspace,'journal.'+status,item)
        return item


def listing(workspace_id, params):
    if set(params)-{'from','to','category','concern','status','page','undated'}: raise ValueError('Unexpected filters.')
    start,end = date.fromisoformat(params['from']),date.fromisoformat(params['to'])
    if not 0 <= (end-start).days <= 365: raise ValueError('Use at most 366 days.')
    page = int(params.get('page','1'))
    if not 1 <= page <= 100000: raise ValueError('Invalid page.')
    rows = JournalEvent.objects.filter(workspace_id=workspace_id)
    status = params.get('status','active')
    if status not in ('active','archived'): raise ValueError('Invalid state.')
    rows = rows.filter(status=status)
    category = params.get('category','')
    if category:
        if category not in ('note','symptom'): raise ValueError('Invalid category.')
        rows = rows.filter(category=category)
    if params.get('concern'):
        concern_obj = concern(workspace_id,params['concern'],params['concern'])
        rows = rows.filter(concern_id=concern_obj)
    undated = params.get('undated','false')
    if undated not in ('true','false'): raise ValueError('Invalid undated filter.')
    rows = rows.annotate(lower_date=RawSQL('continuity_care_bound(occurrence, false)',[]),
        upper_date=RawSQL('continuity_care_bound(occurrence, true)',[]))
    dated = Q(lower_date__lte=end,upper_date__gte=start)
    rows = rows.filter(dated | Q(occurrence__precision='unknown')) if undated=='true' else rows.filter(dated)
    # Approximate and undated entries keep their original precision; bounds are query-only.
    rows = rows.order_by('-lower_date','-created_at','-id')
    selected = list(rows[(page-1)*30:page*30+1])
    return {'contract_version':1,'items':[payload(item) for item in selected[:30]],
        'next_page':page+1 if len(selected)>30 else None,'from':start,'to':end}


def draft_payload(item):
    return {'contract_version':1,'draft':None if item is None else {'id':item.pk,'revision':item.revision,
        'event_id':item.event_id,'base_revision':item.base_revision,'fields':item.fields,'updated_at':item.updated_at}}


def save_draft(user, workspace_id, fields, expected_revision, event_id, base_revision):
    revision(expected_revision); revision(base_revision)
    if not isinstance(fields,dict) or set(fields)!=set(DRAFT_FIELDS): raise ValueError('Unexpected draft fields.')
    if any(not isinstance(fields[key],str) or len(fields[key])>limit for key,limit in DRAFT_FIELDS.items()):
        raise ValueError('Invalid draft fields.')
    if fields['category'] not in ('note','symptom') or fields['precision'] not in ('unknown','year','month','day'):
        raise ValueError('Invalid draft category or date precision.')
    with transaction.atomic():
        workspace = authorize(user,workspace_id,lock=True)
        item = JournalDraft.objects.select_for_update().filter(workspace=workspace).first()
        if expected_revision!=(item.revision if item else 0): raise services.Conflict('Recovery draft changed.')
        if event_id is not None:
            if not isinstance(event_id,str) or not event_id or base_revision<1: raise ValueError('Invalid edited entry binding.')
            try: event = JournalEvent.objects.filter(pk=event_id,workspace=workspace).first()
            except (ValidationError,ValueError): raise ValueError('Invalid event.') from None
            if event is None: raise Http404
        elif base_revision!=0: raise ValueError('New entry has no revision.')
        if fields['concern_id']: concern(workspace,fields['concern_id'],fields['concern_id'])
        if item:
            item.fields=fields.copy(); item.event_id=event_id; item.base_revision=base_revision
            item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=['fields','event_id','base_revision','revision','updated_by','updated_at'])
        else:
            item=JournalDraft.objects.create(workspace=workspace,updated_by=user,fields=fields.copy(),event_id=event_id,base_revision=base_revision)
        services.audit(user,workspace,'journal.draft.save',item)
        return item


def discard_draft(user,workspace_id,expected_revision):
    revision(expected_revision)
    with transaction.atomic():
        workspace=authorize(user,workspace_id,lock=True)
        item=JournalDraft.objects.select_for_update().filter(workspace=workspace).first()
        if not item or item.revision!=expected_revision: raise services.Conflict('Recovery draft changed.')
        services.audit(user,workspace,'journal.draft.discard',item)
        item.delete()
