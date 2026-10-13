"""Explicit, bounded assistant requests and immutable source snapshots."""
import hashlib
import json
import re
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from .glossary import ENTRIES, VERSION as GLOSSARY_VERSION
from .metadata import FIELDS, assertion_value
from .models import (AssistantSource, AssistantTask, ConsultationPacket, ImageInspection,
                     SourceRecord, SourceVersion, TextExtraction)
from .services import Conflict, audit, authorize
from .storage import read_original

SOURCE_LIMIT = 30
TEXT_LIMIT = 2000
CONTEXT_LIMIT = 48000


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def authority(user, workspace_id, kind, lock=False):
    result=authorize(user,workspace_id,lock=lock)
    if kind=='packet_overview':
        authorize(user,workspace_id,'prepare_packet',lock=lock)
    return result


def compact_text(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True) if not isinstance(value,str) else value


def source_chunks(version, label, assertions, budget):
    chunks=[]
    remaining=min(budget,4000)
    truncated=False
    def add(text,locator):
        nonlocal remaining,truncated
        if not text:
            return
        text=compact_text(text)
        if remaining<=0:
            truncated=True
            return
        if len(text)>remaining:
            truncated=True
            text=text[:remaining]
        chunks.append({'id':f'{label}-c{len(chunks)}','text':text,'locator':locator})
        remaining-=len(text)
    add(version.original_filename,{'kind':'uploaded_filename'})
    for field in FIELDS:
        assertion=assertions.get(field)
        if assertion:
            add(assertion_value(assertion),{'kind':'patient_confirmed_metadata','field':field,'assertion_id':str(assertion.pk)})
    inspection=ImageInspection.objects.filter(source_version=version).first()
    if inspection:
        for field,item in inspection.details.get('header_fields',{}).items():
            # Identifiers/descriptions stay out of inference; only explicit technical labels.
            if field in ('Modality','StudyDate','InstitutionName'):
                add(item['value'],{'kind':'unverified_dicom_header','tag':item['tag'],'field':field})
    extraction=TextExtraction.objects.filter(source_version=version).first()
    text_remaining=TEXT_LIMIT
    if extraction:
        for page in extraction.pages:
            text=page['text']
            if len(text)>text_remaining:
                truncated=True
            piece=text[:text_remaining]
            add(piece,{'kind':'source_text','page':page['page']})
            text_remaining-=len(piece)
        if text_remaining<=0:
            truncated=True
    return chunks,extraction,truncated,sum(len(c['text']) for c in chunks)


def create_task(user,workspace_id,kind,parameters):
    if kind not in ('search','packet_overview','explain_term') or not isinstance(parameters,dict):
        raise ValueError('Unsupported assistant request.')
    authority(user,workspace_id,kind)
    if kind=='search':
        if set(parameters)!={'query'} or not isinstance(parameters['query'],str) or not 1<=len(parameters['query'].strip())<=240:
            raise ValueError('Provide a search query up to 240 characters.')
        parameters={'query':parameters['query'].strip()}
    elif kind=='packet_overview':
        if set(parameters)!={'packet_id'}:
            raise ValueError('Select a packet.')
    elif set(parameters)!={'source_version_id','term'} or not isinstance(parameters['term'],str) or not 1<=len(parameters['term'].strip())<=80:
        raise ValueError('Select a record and a term up to 80 characters.')
    try:
        with transaction.atomic():
            workspace,_=authority(user,workspace_id,kind,lock=True)
            active=AssistantTask.objects.filter(workspace=workspace,requested_by=user,kind=kind,state__in=['queued','processing','waiting_model']).first()
            if active:
                raise Conflict('An assistant request of this kind is already pending. View or cancel it before creating another.')
            revision=None
            selected=[]
            if kind=='search':
                records=SourceRecord.objects.filter(workspace=workspace,current_version__isnull=False).order_by('-created_at','id')
                total=records.count()
                selected=[(record.current_version,None) for record in records.select_related('current_version')[:SOURCE_LIMIT]]
            elif kind=='packet_overview':
                packet=ConsultationPacket.objects.filter(workspace=workspace,pk=parameters['packet_id']).first()
                if not packet:
                    raise Http404
                revision=packet.revisions.get(state='approved')
                selected=[(item.source_version,{field:getattr(item,field) for field in FIELDS})
                    for item in revision.items.select_related('source_version',*FIELDS).order_by('created_at','id')]
                total=len(selected)
                parameters={'packet_id':str(packet.pk)}
            else:
                version=SourceVersion.objects.filter(workspace=workspace,pk=parameters['source_version_id']).first()
                if not version:
                    raise Http404
                parameters={'source_version_id':str(version.pk),'term':parameters['term'].strip()}
                selected=[(version,None)]
                total=1
            if not selected or len(selected)>SOURCE_LIMIT:
                raise ValueError('Select between one and 30 records.')
            snapshots=[]
            budget=CONTEXT_LIMIT
            truncated_count=0
            for number,(version,assertions) in enumerate(selected):
                head=version.metadata_head
                assertions=assertions if assertions is not None else {field:getattr(head,field) for field in FIELDS}
                label=f's{number+1}'
                chunks,extraction,truncated,used=source_chunks(version,label,assertions,budget)
                budget-=used
                truncated_count+=int(truncated)
                snapshots.append((version,label,chunks,extraction,head.revision))
            if kind=='explain_term':
                term=parameters['term']
                candidates=[key for key,entry in ENTRIES.items() if term.casefold() in {alias.casefold() for alias in entry['aliases']}]
                if not candidates:
                    raise ValueError('This term is not yet in the reviewed glossary.')
                pattern=re.compile(r'(?<!\w)'+re.escape(term)+r'(?!\w)',re.I)
                if not any(pattern.search(chunk['text']) for _,_,chunks,_,_ in snapshots for chunk in chunks):
                    raise ValueError('The term must occur in the selected source context.')
                parameters['definition_ids']=candidates
            coverage={'accessible_records_at_request':total,'included_records':len(selected),
                'record_limit':SOURCE_LIMIT,'truncated_sources':truncated_count,
                'text_chars_per_source':TEXT_LIMIT,'text_available_sources':sum(extraction is not None for _,_,_,extraction,_ in snapshots),
                'snapshot':True,'imaging_pixels_included':False}
            limited=kind=='packet_overview' and coverage['text_available_sources']==0 and all(version.content_kind=='medical_image' for version,_ in selected)
            completion={}
            if limited:
                for version,_ in selected:
                    read_original(version)
                completion={'state':'completed','finished_at':timezone.now(),'prompt_version':'packet-overview-preflight-v1',
                    'configuration':{'engine':'input_preflight','model_generation_performed':False,
                        'source_snapshots':[{'source_version_id':str(version.pk),'snapshot_sha256':digest(chunks)} for version,_,chunks,_,_ in snapshots]},
                    'result':{'items':[],'abstained':True,'limitation_code':'no_readable_report_text','status':'report_text_needed',
                        'packet_revision_id':str(revision.pk),'modifies_packet':False}}
            task=AssistantTask.objects.create(workspace=workspace,requested_by=user,kind=kind,
                parameters=parameters,coverage=coverage,packet_revision=revision,**completion)
            for version,label,chunks,extraction,metadata_revision in snapshots:
                AssistantSource.objects.create(workspace=workspace,task=task,source_version=version,source_label=label,
                    extraction=extraction,chunks=chunks,metadata_revision=metadata_revision,snapshot_sha256=digest(chunks))
            audit(user,workspace,'assistant.request',task)
            if limited:
                audit(user,workspace,'assistant.input_limited',task)
            return task
    except IntegrityError:
        raise Conflict('Another assistant request of this kind is pending.') from None


def get_task(user,workspace_id,task_id,lock=False):
    authorize(user,workspace_id)
    rows=AssistantTask.objects.select_for_update() if lock else AssistantTask.objects
    task=rows.filter(workspace_id=workspace_id,pk=task_id,requested_by=user).first()
    if not task:
        raise Http404
    authority(user,workspace_id,task.kind,lock=lock)
    return task


def cancel_task(user,workspace_id,task_id):
    with transaction.atomic():
        task=get_task(user,workspace_id,task_id,lock=True)
        if task.state not in ('queued','processing','waiting_model'):
            raise Conflict('This request has already finished.')
        from django.utils import timezone
        task.state='failed'
        task.safe_error_code='cancelled_by_user'
        task.finished_at=timezone.now()
        task.save(update_fields=['state','safe_error_code','finished_at'])
        audit(user,task.workspace,'assistant.cancel',task)
        return task


def task_context(task):
    sources=list(task.sources.select_related('source_version').order_by('source_label'))
    if not sources:
        raise ValueError('Missing source snapshots.')
    for source in sources:
        if digest(source.chunks)!=source.snapshot_sha256:
            raise ValueError('Source snapshot integrity failed.')
    context={'task':task.kind,'request':task.parameters,'coverage':task.coverage,
        'sources':[{'source_id':source.source_label,'chunks':[{'chunk_id':c['id'],'text':c['text'],'origin':c['locator']['kind']} for c in source.chunks]} for source in sources]}
    if task.kind=='explain_term':
        context['reviewed_definitions']={key:{'title':ENTRIES[key]['title'],'definition':ENTRIES[key]['definition']} for key in task.parameters['definition_ids']}
        context['glossary_version']=GLOSSARY_VERSION
    return context,sources


def checked_citations(values,sources,source_label=None,term=None):
    if not isinstance(values,list) or not 1<=len(values)<=4:
        raise ValueError('Citations required.')
    chunks={chunk['id']:(source,chunk) for source in sources for chunk in source.chunks}
    citations=[]
    for value in values:
        if not isinstance(value,dict) or set(value)!={'chunk_id','quote'}:
            raise ValueError('Invalid citation shape.')
        source,chunk=chunks[value['chunk_id']]
        quote=value['quote']
        if source_label is not None and source.source_label!=source_label:
            raise ValueError('Citation belongs to another match.')
        if not isinstance(quote,str) or not quote.strip() or len(quote)>500 or quote not in chunk['text']:
            raise ValueError('Citation quote does not occur in the selected source.')
        if term and not re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',quote,re.I):
            raise ValueError('Citation does not contain the selected term.')
        version=source.source_version
        citations.append({'source_version_id':str(version.pk),'source_sha256':version.sha256,
            'original_filename':version.original_filename,'quote':quote,'locator':chunk['locator'],
            'download_url':f'/api/workspaces/{task_workspace(source)}/versions/{version.pk}/original/'})
    return citations


def task_workspace(source):
    return source.workspace_id


def validate_response(task,payload,sources):
    if not isinstance(payload,dict) or type(payload.get('abstained')) is not bool:
        raise ValueError('Invalid assistant result.')
    labels={source.source_label:source for source in sources}
    if task.kind=='search':
        if set(payload)!={'matches','abstained'} or not isinstance(payload['matches'],list) or len(payload['matches'])>10:
            raise ValueError('Invalid search result.')
        matches=[]
        seen=set()
        for item in payload['matches']:
            if not isinstance(item,dict) or set(item)!={'source_id','reason','citations'} or item['source_id'] not in labels or item['source_id'] in seen:
                raise ValueError('Invalid source selection.')
            if not isinstance(item['reason'],str) or not 1<=len(item['reason'])<=500:
                raise ValueError('Invalid search reason.')
            source=labels[item['source_id']]
            seen.add(item['source_id'])
            matches.append({'source_version_id':str(source.source_version_id),'reason':item['reason'],
                'citations':checked_citations(item['citations'],sources,item['source_id'])})
        if payload['abstained']!= (not matches):
            raise ValueError('Invalid abstention.')
        return {'matches':matches,'abstained':payload['abstained']}
    if task.kind=='packet_overview':
        if set(payload)!={'items','abstained'} or not isinstance(payload['items'],list) or len(payload['items'])>8:
            raise ValueError('Invalid overview.')
        items=[]
        for item in payload['items']:
            if not isinstance(item,dict) or set(item)!={'text','citations'} or not isinstance(item['text'],str) or not 1<=len(item['text'])<=700:
                raise ValueError('Invalid overview item.')
            items.append({'text':item['text'],'citations':checked_citations(item['citations'],sources)})
        if payload['abstained']!=(not items):
            raise ValueError('Invalid abstention.')
        return {'items':items,'abstained':payload['abstained'],'status':'draft_for_patient_review',
            'packet_revision_id':str(task.packet_revision_id),'modifies_packet':False}
    if set(payload)!={'definition_id','citations','abstained'}:
        raise ValueError('Invalid term explanation.')
    if payload['abstained']:
        if payload['definition_id'] is not None or payload['citations']!=[]:
            raise ValueError('Invalid abstention.')
        return {'abstained':True,'explanation':None}
    key=payload['definition_id']
    if key not in task.parameters['definition_ids']:
        raise ValueError('Unreviewed definition.')
    entry=ENTRIES[key]
    return {'abstained':False,'title':entry['title'],'explanation':entry['definition'],
        'reference':{'title':'MedlinePlus — '+entry['title'],'url':entry['url'],'glossary_version':GLOSSARY_VERSION},
        'citations':checked_citations(payload['citations'],sources,term=task.parameters['term']),
        'scope':'general definition; no interpretation of personal results'}
