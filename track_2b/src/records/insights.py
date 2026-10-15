"""Authorized live projections and deterministic observation counts; no AI or duplicate history."""
import uuid
from datetime import date, timedelta
from django.db import connection
from django.db.models import Count, Min, Max
from django.http import Http404
from django.utils import timezone
from identity.authorization import can_access_workspace
from .care_services import authorize
from .metadata import UNKNOWN_DATE, assertion_value
from .models import (JournalEvent, SourceVersion, MedicationEntry,
    PatientHealthConcern, CareEpisode, CareTeamAssignment, ClinicalContribution)

KINDS=('journal','note','symptom','document','medication','concern','episode','care_relationship')
PAGE_SIZE=30
DATE_UNKNOWN="jsonb_build_object('precision','unknown','year',NULL,'month',NULL,'day',NULL)"


def date_sql(alias):
    return f"jsonb_build_object('precision',COALESCE({alias}.date_precision,'unknown'),'year',{alias}.value_year,'month',{alias}.value_month,'day',{alias}.value_day)"


def selected_id(model, workspace, value):
    if not value: return None
    try: key=uuid.UUID(value)
    except (ValueError,TypeError,AttributeError): raise ValueError('Invalid history filter.') from None
    if not model.objects.filter(workspace_id=workspace,pk=key).exists(): raise Http404
    return key


def filters(user, workspace_id, params, summary=False):
    authorize(user,workspace_id)
    allowed={'from','to','concern'} if summary else {'from','to','concern','episode','kind','origin','date_scope','document_type','page'}
    if set(params)-allowed: raise ValueError('Unexpected Insights filters.')
    try: start,end=date.fromisoformat(params.get('from','')),date.fromisoformat(params.get('to',''))
    except (ValueError,TypeError): raise ValueError('Choose valid start and end dates.') from None
    if not 0<=(end-start).days<=365: raise ValueError('Use a range of at most 366 days.')
    result={'from':start,'to':end,'concern':selected_id(PatientHealthConcern,workspace_id,params.get('concern'))}
    if summary: return result
    kind=params.get('kind','');origin=params.get('origin','');scope=params.get('date_scope','dated')
    if kind and kind not in KINDS: raise ValueError('Invalid event type.')
    if origin not in ('','patient_reported','source_record') or scope not in ('dated','undated'): raise ValueError('Invalid history filter.')
    document_type=params.get('document_type','')
    from .metadata import TYPES
    if document_type and document_type not in TYPES: raise ValueError('Invalid document type.')
    page=int(params.get('page','1'))
    if not 1<=page<=10000: raise ValueError('Invalid page.')
    result.update(kind=kind,origin=origin,date_scope=scope,page=page,document_type=document_type,
        episode=selected_id(CareEpisode,workspace_id,params.get('episode')),
        medications=can_access_workspace(user,workspace_id,'manage_medications'))
    return result


def projection(workspace_id, include_medications):
    # Fixed SQL fragments only. Workspace/filter values always remain bound parameters.
    pieces=[
        "SELECT 'journal'::text kind,id,occurrence parts,created_at recorded_at,concern_id,NULL::uuid episode_id,category,''::text document_type FROM journal_events WHERE workspace_id=%s AND status='active'",
        f"SELECT 'document',v.id,{date_sql('a')},v.created_at,NULL::uuid,NULL::uuid,'',COALESCE(t.value_text,'') FROM source_records r JOIN source_versions v ON v.id=r.current_version_id AND v.workspace_id=r.workspace_id JOIN metadata_heads h ON h.source_version_id=v.id AND h.workspace_id=v.workspace_id LEFT JOIN metadata_assertions a ON a.id=h.document_date_id AND a.workspace_id=v.workspace_id LEFT JOIN metadata_assertions t ON t.id=h.document_type_id AND t.workspace_id=v.workspace_id WHERE r.workspace_id=%s",
        "SELECT 'concern',id,onset,created_at,id,NULL::uuid,'','' FROM patient_health_concerns WHERE workspace_id=%s AND status='active'",
        f"SELECT 'episode',id,{DATE_UNKNOWN},created_at,NULL::uuid,id,'','' FROM care_episodes WHERE workspace_id=%s",
        "SELECT 'care_relationship',id,start_date,created_at,concern_id,NULL::uuid,'','' FROM care_team_assignments WHERE workspace_id=%s AND status='active'",
    ]
    if include_medications:
        pieces.append(f"SELECT 'medication',m.id,{date_sql('m')},m.created_at,NULL::uuid,m.episode_id,'','' FROM medication_entries m WHERE m.workspace_id=%s AND m.status='active'")
    args=[workspace_id]*len(pieces)
    return "WITH history AS ("+' UNION ALL '.join(pieces)+"), bounded AS (SELECT *,continuity_care_bound(parts,false) lower_date,continuity_care_bound(parts,true) upper_date FROM history)",args


def where_clause(f):
    clauses=[];args=[]
    if f['kind'] in ('note','symptom'):
        clauses.append("kind='journal' AND category=%s");args.append(f['kind'])
    elif f['kind']: clauses.append('kind=%s');args.append(f['kind'])
    if f['origin']:
        clauses.append("kind='document'" if f['origin']=='source_record' else "kind<>'document'")
    if f['concern']:
        # Only explicit existing links. A common name/date is never an association.
        clauses.append("concern_id=%s");args.append(f['concern'])
    if f['episode']:
        clauses.append("(episode_id=%s OR (kind='document' AND EXISTS (SELECT 1 FROM episode_sources s WHERE s.episode_id=%s AND s.source_version_id=bounded.id)))")
        args.extend([f['episode'],f['episode']])
    if f['document_type']:
        clauses.append("kind='document' AND document_type=%s");args.append(f['document_type'])
    return (' AND '.join('('+clause+')' for clause in clauses) or 'TRUE'),args


def envelope(item,kind,title,description,parts,date_meaning,provenance,review,href,**extra):
    return {'id':f'{kind}:{item.pk}','kind':kind,'source_id':item.pk,'workspace_id':item.workspace_id,
        'title':title,'description':description,'occurrence':parts or UNKNOWN_DATE,
        'date_meaning':date_meaning,'recorded_at':item.created_at,'provenance':provenance,
        'review_status':review,'visibility':'private','href':href,'original_url':None,
        'source_version_id':None,'concern_id':None,'episode_id':None,'details':[],**extra}


def serialize(rows,workspace_id):
    ids={kind:[key for row_kind,key in rows if row_kind==kind] for kind in ('journal','document','medication','concern','episode','care_relationship')}
    groups={
        'journal':JournalEvent.objects.filter(workspace_id=workspace_id,pk__in=ids['journal']).select_related('concern'),
        'document':SourceVersion.objects.filter(workspace_id=workspace_id,pk__in=ids['document']).select_related('record','metadata_head__document_date','metadata_head__document_type','metadata_head__facility_name'),
        'medication':MedicationEntry.objects.filter(workspace_id=workspace_id,pk__in=ids['medication']).select_related('episode','source_version'),
        'concern':PatientHealthConcern.objects.filter(workspace_id=workspace_id,pk__in=ids['concern']),
        'episode':CareEpisode.objects.filter(workspace_id=workspace_id,pk__in=ids['episode']).annotate(linked_count=Count('sources')),
        'care_relationship':CareTeamAssignment.objects.filter(workspace_id=workspace_id,pk__in=ids['care_relationship']).select_related('practitioner','concern'),
    }
    lookup={(kind,item.pk):item for kind,query in groups.items() for item in query}
    accepted=set(ClinicalContribution.objects.filter(workspace_id=workspace_id,state='accepted',accepted_source_id__in=ids['document']).values_list('accepted_source_id',flat=True))
    root=f'/app/workspaces/{workspace_id}'
    output=[]
    def detail(label,value): return {'label':label,'value':str(value)}
    for kind,key in rows:
        item=lookup.get((kind,key))
        if item is None: continue
        if kind=='journal':
            output.append(envelope(item,kind,'Symptom observation' if item.category=='symptom' else 'Personal note',item.description,item.occurrence,
                'Patient-reported occurrence','patient_reported','Patient-authored observation',f'{root}/journal/{item.pk}',
                concern_id=item.concern_id,details=[detail('Severity','Not recorded' if item.severity is None else f'{item.severity} / 10'),
                    detail('Revision',item.revision),detail('Local time',f'{item.occurrence_time:%H:%M} · {item.timezone_name}' if item.occurrence_time else 'Time not recorded')]))
        elif kind=='document':
            head=item.metadata_head
            parts=assertion_value(head.document_date)
            type_value=assertion_value(head.document_type) or 'Type not reviewed'
            facility=assertion_value(head.facility_name) or 'Issuing facility unknown'
            submitted=item.pk in accepted
            output.append(envelope(item,kind,item.original_filename,f'{type_value.replace("_"," ")} · {facility}',parts,
                'Patient-reviewed document date' if head.revision else 'Document date (details need review)','accepted_contribution' if submitted else 'uploaded_record',
                'Patient-reviewed details; not clinical verification' if head.revision else 'Document details need review',f'{root}/records/{item.record_id}',
                source_version_id=item.pk,original_url=f'/api/workspaces/{workspace_id}/versions/{item.pk}/original/',
                details=[detail('Original version',item.version_number),detail('Source attribution','Accepted submitted document; professional identity unverified' if submitted else 'Uploaded original'),detail('Metadata revision',head.revision)]))
        elif kind=='medication':
            labels={'reported_prescribed':'Reported prescribed; actual use not established','reported_taken':'Patient reported taking this medicine','not_taken':'Patient reported not taking this medicine','unknown':'Medication use unknown'}
            output.append(envelope(item,kind,item.medicine_name,labels[item.use_status],
                {'precision':item.date_precision,'year':item.value_year,'month':item.value_month,'day':item.value_day},
                'Patient-reported medication visit date','patient_reported','Not a verified prescription or intake event',f'/workspaces/{workspace_id}/medications/',
                episode_id=item.episode_id,source_version_id=item.source_version_id,
                original_url=f'/api/workspaces/{workspace_id}/versions/{item.source_version_id}/original/' if item.source_version_id else None,
                details=[detail('Reported dose',item.dose or 'Not recorded'),detail('Reported frequency',item.frequency or 'Not recorded'),
                    detail('Reported route',item.route or 'Not recorded'),detail('Notes',item.instructions or 'None recorded')]))
        elif kind=='concern':
            output.append(envelope(item,kind,item.title,item.description,item.onset,'Patient-reported onset','patient_reported',
                'Unconfirmed concern' if item.certainty=='unconfirmed' else 'Patient-reported diagnosis; not clinically verified',f'{root}/care/concerns',concern_id=item.pk,
                details=[detail('Concern type',item.kind),detail('Revision',item.revision)]))
        elif kind=='episode':
            output.append(envelope(item,kind,item.title,'A private care grouping; an occurrence or appointment date has not been recorded.',UNKNOWN_DATE,
                'Occurrence date not recorded','patient_reported','Patient-created grouping',f'/workspaces/{workspace_id}/',episode_id=item.pk,
                details=[detail('Exact original links',item.linked_count)]))
        else:
            output.append(envelope(item,kind,item.practitioner.name,f'{item.role} · {item.participation} care participation',item.start_date,
                'Patient-reported relationship start','patient_reported','Reported relationship; professional identity unverified',f'{root}/care/team',concern_id=item.concern_id,
                details=[detail('Specialty',item.practitioner.specialty or 'Not recorded'),detail('Facility',item.practitioner.facility or 'Not recorded')]))
    return output


def timeline(user,workspace_id,params):
    f=filters(user,workspace_id,params)
    sql,args=projection(workspace_id,f['medications'])
    clause,bound=where_clause(f)
    period='lower_date<=%s AND upper_date>=%s'
    with connection.cursor() as cursor:
        cursor.execute(sql+f' SELECT COUNT(*) FILTER (WHERE {period}),COUNT(*) FILTER (WHERE lower_date IS NULL) FROM bounded WHERE '+clause,
            [*args,f['to'],f['from'],*bound])
        dated_count,undated_count=cursor.fetchone()
        scope=period if f['date_scope']=='dated' else 'lower_date IS NULL'
        scope_args=[f['to'],f['from']] if f['date_scope']=='dated' else []
        cursor.execute(sql+f' SELECT kind,id FROM bounded WHERE ({clause}) AND ({scope}) ORDER BY lower_date DESC NULLS LAST,recorded_at DESC,kind,id LIMIT %s OFFSET %s',
            [*args,*bound,*scope_args,PAGE_SIZE+1,(f['page']-1)*PAGE_SIZE])
        rows=cursor.fetchall()
    return {'contract_version':1,'items':serialize(rows[:PAGE_SIZE],workspace_id),
        'next_page':f['page']+1 if len(rows)>PAGE_SIZE else None,'page':f['page'],
        'dated_count':dated_count,'undated_count':undated_count,'date_scope':f['date_scope'],
        'generated_at':timezone.now(),'medications_included':f['medications'],
        'coverage':{'current_document_versions_only':True,'drafts_excluded':True,'archived_entries_excluded':True,
            'concern_links_are_explicit':True,'episode_dates_not_inferred':True}}


def observations(user,workspace_id,params):
    f=filters(user,workspace_id,params,summary=True)
    all_rows=JournalEvent.objects.filter(workspace_id=workspace_id,status='active',category='symptom')
    if f['concern']: all_rows=all_rows.filter(concern_id=f['concern'])
    # Exact dates alone can support daily bins. Partial dates overlap but do not invent days.
    from django.db.models.expressions import RawSQL
    all_rows=all_rows.annotate(lower_date=RawSQL('continuity_care_bound(occurrence,false)',[]),
        upper_date=RawSQL('continuity_care_bound(occurrence,true)',[]))
    overlapping=all_rows.filter(lower_date__lte=f['to'],upper_date__gte=f['from'])
    partial=overlapping.exclude(occurrence__precision='day').count()
    undated=all_rows.filter(occurrence__precision='unknown').count()
    exact=overlapping.filter(occurrence__precision='day')
    aggregate=exact.values('lower_date').annotate(observations=Count('id'),scored=Count('severity'),
        minimum=Min('severity'),maximum=Max('severity')).order_by('lower_date')
    by_date={row['lower_date']:row for row in aggregate}
    days=(f['to']-f['from']).days+1
    bins=[]
    for index in range(days):
        day=f['from']+timedelta(days=index);row=by_date.get(day)
        bins.append({'date':day,'observations':row['observations'] if row else 0,
            'scored_observations':row['scored'] if row else 0,
            'severity_min':row['minimum'] if row else None,'severity_max':row['maximum'] if row else None})
    count=sum(row['observations'] for row in bins);scored=sum(row['scored_observations'] for row in bins)
    return {'contract_version':1,'from':f['from'],'to':f['to'],'concern_id':f['concern'],
        'exact_dated_observations':count,'days_with_observations':len(by_date),'days_in_range':days,
        'days_without_entries':days-len(by_date),'scored_observations':scored,'unscored_observations':count-scored,
        'partial_date_observations_excluded':partial,'undated_observations_excluded':undated,
        'chart_ready':len(by_date)>=3,'bins':bins,'method':'active_patient_reported_symptom_entries_by_exact_local_date_v1',
        'interpretation':'Counts describe recorded observations, not unique symptom episodes. Unrecorded days and absent scores are unknown. Different entries may describe different symptoms. No diagnosis, adherence or causal inference.'}
