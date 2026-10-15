"""Resumable population and workflow receipts using existing HTTP APIs only."""
import json
import time
from .prepare import PUBLIC,RUNTIME,VERSION,sha,write_json,validate_manifest
from . import environment as env
from .client import Client,provision


def load():
    value=json.loads((PUBLIC/'population.json').read_text(encoding='utf-8'));validate_manifest(value);return value


def ledger():
    path=RUNTIME/'seed-state.json'
    digest=sha((PUBLIC/'population.json').read_bytes())
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':VERSION,'accounts':{},'documents':{},'operations':{}}
    if state.get('version')!=VERSION or state.get('population_sha256',digest)!=digest:
        raise ValueError('Seed ledger belongs to a different population version')
    state['population_sha256']=digest
    return state


def persist(value): write_json(RUNTIME/'seed-state.json',value)


def selected(suite,profile):
    if profile not in suite['profiles']: raise ValueError('Unknown population profile')
    spec=suite['profiles'][profile]
    patients=[p for p in suite['patients'] if p['id'] in spec['patients']]
    actors=[a for a in suite['actors'] if a['id'] in spec['actors']]
    docs={d['id']:d for d in suite['documents']}
    chosen=[]
    for patient in patients:
        ids=patient['documents'][:spec.get('document_caps',{}).get(patient['id'],10000)]
        chosen.extend(docs[key] for key in ids)
    return patients,actors,chosen


def dry_run(profile):
    suite=load();patients,actors,docs=selected(suite,profile)
    value={'version':VERSION,'profile':profile,'patients':len(patients),'additional_actors':len(actors),
      'initial_documents':len(docs),'per_patient':{p['id']:sum(d['patient']==p['id'] for d in docs) for p in patients},
      'network_or_database_writes':False,'manifest_sha256':sha((PUBLIC/'population.json').read_bytes()),
      'unsupported':['trusted_delegation','journal_events','OCR','professional_verification','voice_controls']}
    write_json(RUNTIME/f'plan-{profile}.json',value);return value


def sign_in(key,state,known):
    client=Client(known[key]).sign_in()
    previous=state['accounts'].get(key)
    binding={'user_id':client.user,'workspace_id':client.workspace,'keycloak_subject':known[key]['keycloak_subject']}
    if previous and previous!=binding: raise ValueError('Stable account-to-workspace mapping changed')
    if any(v['workspace_id']==client.workspace for k,v in state['accounts'].items() if k!=key): raise ValueError('Two fixtures resolved to one workspace')
    state['accounts'][key]=binding;persist(state);return client


def ingest(client,doc,state,version_of=None):
    data=(RUNTIME/doc['prepared_path']).read_bytes()
    if sha(data)!=doc['sha256']: raise ValueError('Prepared source changed')
    previous=state['documents'].get(doc['id'])
    if previous:
        if previous['workspace_id']!=client.workspace or previous['sha256']!=doc['sha256']: raise ValueError('Seed receipt binding changed')
        return previous
    started=time.perf_counter()
    response=client.own('records/' if version_of is None else f'records/{version_of}/versions/',method='POST',
      files={'file':(doc['id']+'.pdf',data,'application/pdf')},expected=(200,201))
    version=response['version']
    receipt={'workspace_id':client.workspace,'record_id':version['record_id'],'version_id':version['id'],
      'sha256':version['sha256'],'upload_seconds':time.perf_counter()-started,'bytes':len(data)}
    if receipt['sha256']!=doc['sha256']: raise ValueError('Uploaded source checksum differs')
    state['documents'][doc['id']]=receipt;persist(state);return receipt


def review(client,doc,state):
    receipt=state['documents'][doc['id']]
    row=client.own(f"records/{receipt['record_id']}/")
    values={'document_type':doc['document_type'],'document_date':doc['document_date'],'facility_name':doc['facility']}
    if row['metadata']['revision']==0:
        client.own(f"records/{receipt['record_id']}/review/",method='POST',data={'source_version_id':receipt['version_id'],
          'expected_revision':0,'values':values})
    elif row['metadata']['values']!=values:
        raise ValueError('Existing reviewed fixture metadata differs; no overwrite performed')
    receipt['reviewed_reference_metadata']=True;persist(state)


def create_once(client,state,key,suffix,field,items_key,values):
    if key in state['operations']: return state['operations'][key]
    rows=client.own(suffix)[items_key]
    candidates=[row for row in rows if (row.get('values',row)).get(field)==values[field]]
    if len(candidates)>1: raise ValueError('Ambiguous existing fixture operation')
    row=candidates[0] if candidates else client.own(suffix,method='POST',data={'values':values,'expected_revision':0},expected=(201,))
    state['operations'][key]=row;persist(state);return row


def enrich(client,patient,state,known):
    key=patient['id'];unknown={'precision':'unknown','year':None,'month':None,'day':None}
    current=client.own('profile/')
    if current['revision']==0:
        values=current['values'];values.update(full_name='Synthetic '+key+' - fictional evaluation',preferred_name='Synthetic '+key)
        client.own('profile/',method='POST',data={'values':values,'expected_revision':0})
    concern=create_once(client,state,key+':concern','care/concerns/','title','items',{
        'title':VERSION+' / '+key,'description':'Authored organizational test context: '+patient['scenario'],
        'kind':'investigation','certainty':'unconfirmed','onset':unknown})
    doctors=[]
    for index in range(2 if key=='P10' else 1):
        doctor=create_once(client,state,f'{key}:doctor:{index}','care/practitioners/','name','items',{
          'name':f'Synthetic reported doctor {key}-{index+1}','specialty':'Not clinically verified',
          'facility':f'Fictional test facility {index+1}','notes':'Authored relationship fixture, not an inferred upstream clinician.'})
        doctors.append(doctor)
        assignment_key=f'{key}:assignment:{index}'
        if assignment_key not in state['operations']:
            existing=client.own('care/assignments/')['items']
            matches=[a for a in existing if a['values']['practitioner_id']==doctor['id'] and a['values']['concern_id']==concern['id']]
            value=matches[0] if matches else client.own('care/assignments/',method='POST',data={'expected_revision':0,'values':{
              'practitioner_id':doctor['id'],'concern_id':concern['id'],'role':'Authored historical relationship',
              'participation':'historical' if index==0 else 'current','start_date':unknown,'end_date':unknown,'notes':'No record access is created.'}},expected=(201,))
            state['operations'][assignment_key]=value;persist(state)
    for actor_key in {'P03':['A05','A06'],'P04':['A07','A08']}.get(key,[]):
        if actor_key not in state['accounts']: continue
        create_once(client,state,key+':contact:'+actor_key,'care-circle/','full_name','contacts',{
          'full_name':VERSION+' '+actor_key,'email':'','phone':'','notes':'Authored reported relationship only; no verified authority.',
          'relationship':'caregiver' if key=='P03' else 'guardian','is_next_of_kin':False,'is_emergency_contact':False,
          'recipient_id':state['accounts'][actor_key]['user_id']})
    if key in ('P01','P15'):
        for index,use in ((1,'reported_prescribed'),(2,'not_taken')) if key=='P15' else ((2,'reported_prescribed'),):
            doc_id=f'{key}-X-{index:03d}'
            if doc_id not in state['documents']: continue
            create_once(client,state,f'{key}:medicine:{index}','medications/','instructions','medications',{
              'medicine_name':'Medicine Z (fictional)' if key=='P15' else 'Medicine Q (fictional)',
              'dose':'10 mg' if key=='P15' and index==1 else 'Not reported' if key=='P15' else '5 mg',
              'frequency':'Not reported','route':'Not reported','instructions':VERSION+f' {key} medicine reference {index}',
              'use_status':use,'visit_date':unknown,'episode_id':None,'source_version_id':state['documents'][doc_id]['version_id']})


@env.exclusive
def seed(profile,max_documents=32):
    env.guard();suite=load();patients,actors,docs=selected(suite,profile)
    if profile=='stress':
        gate=RUNTIME/'functional-ready.json'
        if not gate.is_file() or not json.loads(gate.read_text(encoding='utf-8')).get('approved_for_stress'): raise ValueError('Functional stability review required before stress seeding')
        if len(patients)<50: raise ValueError('Prepare a separate expanded stress manifest first; no false 50-patient claim')
    known=provision(patients+actors);state=ledger();clients={}
    try:
        for person in patients+actors: clients[person['id']]=sign_in(person['id'],state,known)
        count=0
        for doc in docs:
            if doc['id'] not in state['documents'] and count>=max_documents: continue
            if doc['id'] not in state['documents']:
                ingest(clients[doc['patient']],doc,state);count+=1
                print(json.dumps({'uploaded':count,'profile':profile,'fixture':doc['id']}),flush=True)
        for person in patients:
            if person['id']!='P14': enrich(clients[person['id']],person,state,known)
        result={'profile':profile,'new_uploads':count,'selected_documents':len(docs),
            'completed_selected_documents':sum(d['id'] in state['documents'] for d in docs),'bound_accounts':len(state['accounts'])}
        write_json(RUNTIME/f'seed-{profile}.json',result);return result
    finally:
        for client in clients.values(): client.close()


@env.exclusive
def verify(profile):
    env.guard();suite=load();patients,actors,docs=selected(suite,profile);state=ledger();known=env.accounts();checks=[]
    for patient in patients:
        client=sign_in(patient['id'],state,known)
        try:
            offset=0;rows=[]
            while True:
                page=client.own('records/search/',method='POST',data={'offset':offset});rows+=page['records']
                if not page['has_more']: break
                offset+=50
            for doc in [d for d in docs if d['patient']==patient['id']]:
                receipt=state['documents'].get(doc['id']);valid=False
                if receipt:
                    response=client.call(f"/api/workspaces/{client.workspace}/versions/{receipt['version_id']}/original/",raw=True)
                    valid=sha(response.content)==doc['sha256']
                checks.append({'case':'immutable-original','patient':patient['id'],'document':doc['id'],'passed':valid})
            checks.append({'case':'pagination-current-records','patient':patient['id'],'observed':len(rows),
              'passed':len(rows)>=sum(d['patient']==patient['id'] for d in docs)})
        finally: client.close()
    result={'profile':profile,'category':'deterministic_data_integrity','checks':checks,
        'passed':all(c['passed'] for c in checks),'manifest_sha256':sha((PUBLIC/'population.json').read_bytes())}
    write_json(RUNTIME/f'verify-{profile}.json',result);return result
