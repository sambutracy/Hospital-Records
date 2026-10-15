"""Integrated receipts: software/permissions, model screens and human review are distinct."""
import json
import re
import statistics
import time
from pathlib import Path
from . import environment as env,run
from .prepare import PUBLIC,RUNTIME,VERSION,write_json,sha
from .client import Client


def case_manifest(suite):
    documents={d['id']:d for d in suite['documents']}
    cases=[]
    for key in ('P01-X-001','P01-X-002','P15-X-008','P15-X-009'):
        doc=documents[key]
        cases.append({'id':'metadata-'+key,'kind':'metadata','patient':doc['patient'],'sources':[key],
          'expected':{'document_type':doc['document_type'],'document_date':doc['document_date'],'facility_name':doc['facility']},
          'expected_evidence':'Authored representation labels and original authored source text, page 1.',
          'unacceptable':['invented dates','prescription interpreted as use'],'clinical_validation':False})
    for key,patient,query,terms in [
      ('q01','P01','Medicine Q',['Medicine Q']),('q02','P02','Find diabetes records',['diabet']),
      ('q03','P13','EVAL-OLDER-000',['EVAL-OLDER-000']),('q04','P15','Medicine Z',['Medicine Z']),
      ('q05','P15','no history of asthma',['no history of asthma']),('q06','P15','cardiac transplant in 2050',['cardiac transplant'])]:
        expected=[];evidence=[]
        for doc in suite['documents']:
            if doc['patient']!=patient or 'text_path' not in doc: continue
            text=(RUNTIME/doc['text_path']).read_text(encoding='utf-8')
            match=next((re.search(re.escape(term),text,re.I) for term in terms if re.search(re.escape(term),text,re.I)),None)
            if match:
                expected.append(doc['id']);evidence.append({'document':doc['id'],'page':1,'quote':text[max(0,match.start()-40):match.end()+60]})
        cases.append({'id':key,'kind':'search','patient':patient,'query':query,'relevant':expected,'expected_evidence':evidence,
          'label_method':'Authored fact references / literal source-span screen, independent of Apertus; not a clinical relevance gold standard',
          'required_uncertainty':'Finding a document is not confirmation of a diagnosis; omitted contexts do not establish absence.'})
    for key,sources,required,forbidden in [
      ('o01',['P01-X-001','P01-X-002'],[['12.1'],['g/dL'],['prescrib','unknown','whether']],['currently takes Medicine Q']),
      ('o02',['P15-X-001','P15-X-002','P15-X-007'],[['10'],['20'],['not tak','non-use','not being taken','not taking'],['conflict','unresolved','differ']],['currently takes Medicine Z']),
      ('o03',['P15-X-003','P15-X-004','P15-X-006'],[['suspect','unconfirm'],['unknown'],['no history','negat','denies']],['confirmed asthma','no allergies'])]:
        cases.append({'id':key,'kind':'packet_overview','patient':sources[0].split('-')[0],'sources':sources,
          'expected_evidence':[{'document':doc,'page':1,'text_path':documents[doc]['text_path']} for doc in sources],
          'required_any':required,'forbidden':forbidden,'expected_access':'private selected-version packet only',
          'semantic_review':'Human entailment review required; phrase/quote validity is insufficient.'})
    result={'version':'comfort-ecosystem-evaluation-v1','population_sha256':sha((PUBLIC/'population.json').read_bytes()),'cases':cases,
      'categories':['software_authorization','deterministic_fixture_checks','actual_model_evaluation','human_semantic_review','human_usability'],
      'frozen_legacy_suites_modified':False}
    target=PUBLIC/'evaluation.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result: raise ValueError('Evaluation is frozen; publish a new version for changed annotations')
    write_json(target,result)
    return extended_cases(suite,result)


def extended_cases(suite,base):
    """Extend the new ecosystem suite without changing its v1 or legacy fixtures."""
    from pypdf import PdfReader
    cases=json.loads(json.dumps(base['cases']))
    docs={d['id']:d for d in suite['documents']}
    relevant=[];evidence=[]
    for doc in suite['documents']:
        if doc['patient']!='P11' or 'text_path' not in doc:continue
        text=(RUNTIME/doc['text_path']).read_text(encoding='utf-8')
        match=re.search(r'\bBP\b',text)
        if match:
            relevant.append(doc['id']);evidence.append({'document':doc['id'],'page':1,'quote':text[match.start():].splitlines()[0]})
    if not relevant:raise ValueError('Abbreviation fixture requires literal upstream BP evidence')
    cases.append({'id':'q07','kind':'search','patient':'P11','query':'Find records mentioning BP',
      'relevant':relevant,'expected_evidence':evidence,
      'label_method':'Literal whole-word BP in independently inspected notes; no inferred clinical meaning',
      'required_uncertainty':'Retrieval does not establish diagnosis or resolve abbreviations.'})
    cases.append({'id':'o04','kind':'packet_overview','patient':'P10','sources':['P10-B-01','P10-B-04'],
      'expected_evidence':[
        {'document':'P10-B-01','page':1,'quote':'The associated entry identifies Dr. Danuta Little as the clinician and'},
        {'document':'P10-B-01','page':1,'quote':'QUICK CARE CLINIC as the facility.'},
        {'document':'P10-B-04','page':1,'quote':'Naproxen sodium 220 MG Oral Tablet'}],
      'required_any':[['salem'],['quick care'],['completed','historical','2021']],
      'forbidden':['currently takes naproxen'],'expected_access':'private selected-version packet only',
      'semantic_review':'Keep provider/date/source attribution and completed medication separate from present use.'})
    cases.append({'id':'o05','kind':'packet_overview','patient':'P01','sources':['P01-X-001','P01-X-002'],
      'expected_evidence':[
        {'document':'P01-X-001','page':1,'quote':'Specimen date: 2026-02-27.'},
        {'document':'P01-X-001','page':1,'quote':'Document date: 2026-03-01'},
        {'document':'P01-X-002','page':1,'quote':'Whether it was taken is unknown.'}],
      'required_any':[['12.1'],['g/dL'],['prescrib'],['unknown'],['2026-02-27','27 feb','february 27']],
      'forbidden':['currently takes Medicine Q'],'expected_access':'private selected-version packet only',
      'semantic_review':'Specimen date differs from report date; prescription does not prove actual use.'})
    # Verify exact reference locations against the actual prepared PDFs. The older
    # v1 metadata is retained unchanged; v2 carries corrected, reproducible locators.
    for case in cases:
        for item in case.get('expected_evidence',[]) if isinstance(case.get('expected_evidence'),list) else []:
            if 'quote' not in item:continue
            pages=PdfReader(RUNTIME/docs[item['document']]['prepared_path']).pages
            needle=' '.join(item['quote'].split())
            matches=[index for index,page in enumerate(pages,1) if needle in ' '.join((page.extract_text() or '').split())]
            if not matches:raise ValueError('Reference quote is not present in prepared source: '+case['id']+' / '+item['document'])
            item['page']=matches[0]
    result={**base,'version':'comfort-ecosystem-evaluation-v2','base_evaluation_sha256':sha((PUBLIC/'evaluation.json').read_bytes()),'cases':cases}
    target=PUBLIC/'evaluation-v2.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Extended evaluation is frozen; publish a new version')
    write_json(target,result)
    # A literal older-note query deliberately targets the first two source notes,
    # outside the ten most recently uploaded records. The earlier EVAL-OLDER
    # marker case is retained, but is not misrepresented as that recency test.
    phrase='No current medications reported'
    older=[];evidence=[]
    for doc in suite['documents']:
        if doc['patient']!='P13' or 'text_path' not in doc:continue
        text=(RUNTIME/doc['text_path']).read_text(encoding='utf-8')
        if phrase.casefold() in text.casefold():
            start=text.casefold().index(phrase.casefold());quote=text[start:start+len(phrase)]
            pages=PdfReader(RUNTIME/doc['prepared_path']).pages
            locators=[i for i,p in enumerate(pages,1) if ' '.join(quote.split()) in ' '.join((p.extract_text() or '').split())]
            if not locators:raise ValueError('Older-note reference page verification failed')
            older.append(doc['id']);evidence.append({'document':doc['id'],'page':locators[0],'quote':quote})
    if len(older)!=2:raise ValueError('Older-note independent reference changed')
    result={**result,'version':'comfort-ecosystem-evaluation-v3','base_v2_sha256':sha(target.read_bytes()),
      'cases':result['cases']+[{'id':'q08','kind':'search','patient':'P13',
        'query':'Find old notes stating no current medications reported','relevant':older,'expected_evidence':evidence,
        'label_method':'Literal phrase in two oldest independently inspected source notes; neither is among the latest ten uploads',
        'required_uncertainty':'Historical notes do not establish current medication use or absence.'}]}
    target=PUBLIC/'evaluation-v3.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v3 is frozen')
    write_json(target,result)
    controls=[
      {'id':'cq01','kind':'search','patient':'P14','query':'follow-up conversation','relevant':['P14-AUX'],
       'expected_evidence':[{'document':'P14-AUX','page':1,'quote':'Patient reports a follow-up conversation.'}],
       'label_method':'Authored literal reference; one-record context calibration','scope':'compact_control'},
      {'id':'co01','kind':'packet_overview','patient':'P14','sources':['P14-AUX'],
       'expected_evidence':[{'document':'P14-AUX','page':1,'quote':'Patient reports a follow-up conversation.'}],
       'required_any':[['follow-up','follow up'],['report']], 'forbidden':['confirmed diagnosis'],'scope':'compact_control'},
      {'id':'co02','kind':'packet_overview','patient':'P01','sources':['P01-X-001'],
       'expected_evidence':[{'document':'P01-X-001','page':1,'quote':'Haemoglobin: 12.1 g/dL.'}],
       'required_any':[['12.1'],['g/dL']],'forbidden':['anaemia','anemia'],'scope':'compact_control'}]
    result={**result,'version':'comfort-ecosystem-evaluation-v4','base_v3_sha256':sha(target.read_bytes()),'cases':result['cases']+controls}
    target=PUBLIC/'evaluation-v4.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v4 is frozen')
    write_json(target,result)
    followups=[]
    for key in ('q01','o01','q08','co01','co02','q06'):
        reference=next(c for c in result['cases'] if c['id']==key)
        followups.append({**reference,'id':'cpu-'+key,'scope':'local_cpu_followup','baseline_case':key,
            'execution_requirement':'local-evidence-v1; fresh saved task; no replacement of baseline attempt',
            'representation':'extractive selection, not abstractive summary'})
    result={**result,'version':'comfort-ecosystem-evaluation-v5','base_v4_sha256':sha(target.read_bytes()),
        'cases':result['cases']+followups}
    target=PUBLIC/'evaluation-v5.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v5 is frozen')
    write_json(target,result)
    followups=[]
    for key in ('o01','q08','co01'):
        reference=next(c for c in result['cases'] if c['id']==key)
        followups.append({**reference,'id':'cpu2-'+key,'scope':'local_cpu_v2_followup','baseline_case':key,
            'execution_requirement':'local-evidence-v2; fresh saved task; baseline and CPU v1 preserved',
            'representation':'extractive selection with explicit per-source overview groups'})
    result={**result,'version':'comfort-ecosystem-evaluation-v6','base_v5_sha256':sha(target.read_bytes()),
        'cases':result['cases']+followups}
    target=PUBLIC/'evaluation-v6.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v6 is frozen')
    write_json(target,result)
    followups=[]
    for key in ('o01','co01','o02'):
        reference=next(c for c in result['cases'] if c['id']==key)
        followups.append({**reference,'id':'cpu3-'+key,'scope':'local_cpu_v3_followup','baseline_case':key,
            'execution_requirement':'local-evidence-v3; explicit clinical passage prior; fresh saved task',
            'representation':'extractive selection; lexical passage prior has incomplete coverage'})
    result={**result,'version':'comfort-ecosystem-evaluation-v7','base_v6_sha256':sha(target.read_bytes()),
        'cases':result['cases']+followups}
    target=PUBLIC/'evaluation-v7.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v7 is frozen')
    write_json(target,result)
    reference=next(c for c in result['cases'] if c['id']=='co01')
    result={**result,'version':'comfort-ecosystem-evaluation-v8','base_v7_sha256':sha(target.read_bytes()),
        'cases':result['cases']+[{**reference,'id':'cpu4-co01','scope':'local_cpu_v4_followup','baseline_case':'co01',
            'execution_requirement':'local-evidence-v4; mixed clinical/admin narrative retained; fresh saved task',
            'representation':'extractive selection; lexical prior is incomplete'}]}
    target=PUBLIC/'evaluation-v8.json'
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=result:raise ValueError('Evaluation v8 is frozen')
    write_json(target,result);return result


def clients_for(keys,state):
    known=env.accounts();clients={}
    for key in sorted(set(keys)):
        if key in known: clients[key]=run.sign_in(key,state,known)
    return clients


def packet(client,state,key,document_ids,suite):
    op='packet:'+key
    if op in state['operations']: return state['operations'][op]
    docs={d['id']:d for d in suite['documents']+suite.get('auxiliary_documents',[])}
    for key_id in document_ids: run.review(client,docs[key_id],state)
    purpose=VERSION+' '+key
    saved=client.own('packets/')['packets'];matches=[p for p in saved if p['purpose']==purpose]
    result=client.own(f"packets/{matches[0]['id']}/") if matches else client.own('packets/',method='POST',
      data={'purpose':purpose,'source_version_ids':[state['documents'][i]['version_id'] for i in document_ids]},expected=(201,))
    state['operations'][op]=result;run.persist(state);return result


@env.exclusive
def workflows(profile,live=False,max_jobs=16):
    env.guard();suite=run.load();state=run.ledger();patients,actors,docs=run.selected(suite,profile)
    keys=[p['id'] for p in patients]+[a['id'] for a in actors];clients=clients_for(keys,state);checks=[]
    def check(name,condition,**evidence): checks.append({'case':name,'passed':bool(condition),**evidence});write_json(RUNTIME/f'workflows-{profile}.json',{'checks':checks,'complete':False})
    def status(client,path,expected,method='GET',data=None,files=None):
        result=client.call(path,method=method,data=data,files=files,expected=(expected,),raw=True)
        return result.status_code==expected
    try:
        # Canonical own workspaces stay distinct from the records received from others.
        for subject in patients:
            patient=subject['id'];owner=clients[patient]
            other=next((k for k in keys if k!=patient),None)
            if other:
                check('cross-workspace-record-denied:'+patient,status(clients[other],f'/api/workspaces/{owner.workspace}/records/',404))
                check('cross-workspace-assistant-denied:'+patient,status(clients[other],f'/api/workspaces/{owner.workspace}/assistant/tasks/',404))
        if 'A09' in clients:
            for patient in patients:
                check('unrelated-cannot-switch-context:'+patient['id'],not any(c['workspace_id']==clients[patient['id']].workspace for c in clients['A09'].data['contexts']))
        # P14 is intentionally empty before its first supported upload.
        if 'P14' in clients:
            client=clients['P14'];op='P14:onboarding'
            if op not in state['operations']:
                before=client.own('records/search/',method='POST',data={})
                check('new-patient-empty-state-api',before['total']==0)
                run.enrich(client,next(p for p in patients if p['id']=='P14'),state,env.accounts())
                doc=next(d for d in suite['auxiliary_documents'] if d['id']=='P14-AUX')
                run.ingest(client,doc,state);run.review(client,doc,state)
                state['operations'][op]={'initial_count':before['total']};run.persist(state)
            check('onboarding-first-record',client.own('records/search/',method='POST',data={})['total']==1)
            resumed=Client(env.accounts()['P14']).sign_in();check('onboarding-persistence-new-session',resumed.workspace==client.workspace and resumed.own('records/search/',method='POST',data={})['total']==1);resumed.close()
        if {'P02','A01','A02'}<=set(clients):
            owner=clients['P02'];first=[d['id'] for d in docs if d['patient']=='P02'][:2];omitted=[d['id'] for d in docs if d['patient']=='P02'][2]
            bundle=packet(owner,state,'sharing-P02',first,suite)
            existing=owner.own('grants/')['grants']
            def grant(recipient,minutes,purpose):
                # Each workflow invocation has independent temporary grants; never
                # extends/reopens a revoked or expired historical permission.
                return owner.own('grants/',method='POST',data={'kind':'read','target_id':bundle['revision_id'],
                  'recipient_id':clients[recipient].user,'purpose':purpose,'expires_in_minutes':minutes},expected=(201,))
            g1=grant('A01',10,VERSION+' read scope test');g2=grant('A02',1,VERSION+' expiry test')
            state['operations']['latest-sharing-grants']=[g1,g2];run.persist(state)
            share='/api/continuity/shares/'+g1['id']+'/'
            shared=clients['A01'].call(share)
            check('exact-packet-recipient-success',{i['source_version_id'] for i in shared['items']}=={state['documents'][k]['version_id'] for k in first})
            check('second-recipient-cannot-reuse-first-grant',status(clients['A02'],share,404))
            check('packet-omitted-source-denied',status(clients['A01'],share+f"versions/{state['documents'][omitted]['version_id']}/original/",404))
            for item in shared['items']:
                result=clients['A01'].call(item['download_url'],raw=True)
                check('shared-original-integrity:'+item['source_version_id'],sha(result.content)==item['sha256'])
            check('read-only-cannot-submit',status(clients['A01'],f"/api/continuity/contribution-authorities/{g1['id']}/submit/",404,method='POST',data={}))
            owner.own(f"grants/read/{g1['id']}/revoke/",method='POST',data={})
            check('revoked-grant-new-read-denied',status(clients['A01'],share,404))
            # Measure actual elapsed expiry, rather than rewriting the immutable grant.
            import datetime
            expiry=datetime.datetime.fromisoformat(g2['expires_at'].replace('Z','+00:00')).timestamp()
            state['operations']['expiry-check']={'grant_id':g2['id'],'expiry':expiry};run.persist(state)
        if {'P07','A03'}<=set(clients):
            owner=clients['P07'];contributor=clients['A03'];op='P07:contribution-flow'
            if op not in state['operations']:
                episodes=owner.own('episodes/')['episodes'];title=VERSION+' P07 return note'
                matches=[e for e in episodes if e['title']==title]
                episode=matches[0] if matches else owner.own('episodes/',method='POST',data={'title':title},expected=(201,))
                grant=owner.own('grants/',method='POST',data={'kind':'contribute','target_id':episode['id'],
                  'recipient_id':contributor.user,'purpose':VERSION+' independent contribution','expires_in_minutes':30},expected=(201,))
                check('contribution-only-cannot-read-workspace',status(contributor,f'/api/workspaces/{owner.workspace}/records/',404))
                check('contribution-grant-not-read-grant',status(contributor,f"/api/continuity/shares/{grant['id']}/",404))
                receipts=[]
                for key,decision in [('P07-accepted-AUX','accept'),('P07-rejected-AUX','reject')]:
                    doc=next(d for d in suite['auxiliary_documents'] if d['id']==key)
                    existing=[r for r in owner.own('contributions/')['contributions']
                        if r['sha256']==doc['sha256'] and r['submitted_by_id']==contributor.user]
                    if len(existing)>1:raise ValueError('Ambiguous fixture contributions; inspect before resuming')
                    response=existing[0] if existing else contributor.call(f"/api/continuity/contribution-authorities/{grant['id']}/submit/",method='POST',
                        files={'file':(key+'.pdf',(RUNTIME/doc['prepared_path']).read_bytes(),'application/pdf')},expected=(200,201))
                    if response['state']=='pending':
                        before=owner.own('records/search/',method='POST',data={'q':key})
                        check('pending-contribution-not-patient-record:'+decision,before['total']==0)
                        state['operations']['pending-check:'+key]=before['total']==0;run.persist(state)
                        reviewed=owner.own(f"contributions/{response['id']}/review/",method='POST',data={'decision':decision})
                    else:reviewed=response
                    check('patient-contribution-review:'+decision,reviewed['state']==('accepted' if decision=='accept' else 'rejected'))
                    state['operations']['decision:'+key]=reviewed;run.persist(state)
                    if decision=='accept':
                        original=owner.call(f"/api/workspaces/{owner.workspace}/versions/{reviewed['accepted_source_id']}/original/",raw=True)
                        check('accepted-contribution-provenance',sha(original.content)==doc['sha256'] and reviewed['submitted_by_id']==contributor.user)
                    else: check('rejected-contribution-not-library',owner.own('records/search/',method='POST',data={'q':key})['total']==0)
                    receipts.append(reviewed)
                state['operations'][op]=receipts;run.persist(state)
            else: check('contribution-receipts-retained',len(state['operations'][op])==2)
        for patient,actor in [('P03','A05'),('P03','A06'),('P04','A07'),('P04','A08')]:
            if patient in clients and actor in clients:
                check('reported-relationship-not-delegation:'+actor,status(clients[actor],f'/api/workspaces/{clients[patient].workspace}/profile/',404))
                check('reported-role-cannot-request-patient-AI:'+actor,status(clients[actor],f'/api/workspaces/{clients[patient].workspace}/assistant/tasks/',404,method='POST',data={'kind':'search','parameters':{'query':'records'}}))
        # Reported nurse/caregiver labels are not account roles. Explicit read
        # grants work independently, and revoking one does not revoke another.
        for patient,recipients in [('P01',['A04']),('P03',['A05','A06']),('P04',['A07','A08'])]:
            if patient not in clients or not all(k in clients for k in recipients):continue
            owner=clients[patient];first=next(d['id'] for d in docs if d['patient']==patient)
            bundle=packet(owner,state,'reported-recipient-'+patient,[first],suite);grants=[]
            for actor in recipients:
                grant=owner.own('grants/',method='POST',data={'kind':'read','target_id':bundle['revision_id'],
                  'recipient_id':clients[actor].user,'purpose':VERSION+' explicit read '+actor,'expires_in_minutes':10},expected=(201,))
                grants.append((actor,grant))
                shared=clients[actor].call('/api/continuity/shares/'+grant['id']+'/')
                check('explicit-read-for-reported-recipient:'+actor,len(shared['items'])==1)
            actor,grant=grants[-1]
            owner.own('grants/read/'+grant['id']+'/revoke/',method='POST',data={})
            check('reported-recipient-revocation:'+actor,status(clients[actor],'/api/continuity/shares/'+grant['id']+'/',404))
            if len(grants)>1:
                actor,grant=grants[0]
                check('other-recipient-grant-survives:'+actor,clients[actor].call('/api/continuity/shares/'+grant['id']+'/')['grant_id']==grant['id'])
        if 'A10' in clients and 'P01' in clients:
            actor=clients['A10'];doc=next(d for d in suite['auxiliary_documents'] if d['id']=='A10-AUX');run.ingest(actor,doc,state)
            owner=clients['P01'];bundle=packet(owner,state,'dual-role-P01',['P01-X-001'],suite)
            grant=owner.own('grants/',method='POST',data={'kind':'read','target_id':bundle['revision_id'],'recipient_id':actor.user,'purpose':VERSION+' dual role','expires_in_minutes':10},expected=(201,))
            check('dual-role-receives-specific-packet',actor.call('/api/continuity/shares/'+grant['id']+'/')['grant_id']==grant['id'])
            check('dual-role-own-workspace-distinct',actor.workspace!=owner.workspace and actor.own('records/search/',method='POST',data={})['total']>=1)
        expiry=state['operations'].get('expiry-check')
        if expiry and 'A02' in clients:
            remaining=expiry['expiry']-time.time()+0.2
            if remaining>0: time.sleep(min(remaining,60))
            check('expired-grant-denied',status(clients['A02'],'/api/continuity/shares/'+expiry['grant_id']+'/',404))
        result={'profile':profile,'category':'software_authorization','checks':checks,'passed':all(c['passed'] for c in checks),
            'complete':True,'unsupported':['trusted_delegation','journal_events','professional_verification','voice_assistance'],
            'clinical_validation':False,'human_usability_validation':False}
        write_json(RUNTIME/f'workflows-{profile}.json',result);return {'profile':profile,'checks':len(checks),'passed':result['passed']}
    finally:
        for client in clients.values(): client.close()


@env.exclusive
def journeys(profile,live=False,max_jobs=16):
    """Read/review/filter journeys, separate from model accuracy measurements."""
    env.guard();suite=run.load();state=run.ledger();patients,actors,docs=run.selected(suite,profile)
    keys=[p['id'] for p in patients]+(['A02'] if any(a['id']=='A02' for a in actors) else [])
    clients=clients_for(keys,state);checks=[]
    def check(name,value):checks.append({'case':name,'passed':bool(value)})
    try:
        for patient in ('P01','P15'):
            if patient not in clients:continue
            client=clients[patient];selected=[d for d in docs if d['patient']==patient]
            # Explicit authored reference review through the normal revision API;
            # never use a model's own answer as a correctness label.
            for doc in selected:run.review(client,doc,state)
            for kind in sorted({d['document_type'] for d in selected}):
                response=client.own('records/search/',method='POST',data={'document_type':kind})
                check('document-type-filter:'+patient+':'+kind,response['total']==sum(d['document_type']==kind for d in selected))
            response=client.own('records/search/',method='POST',data={'document_year':2026})
            check('document-year-preserves-unknown:'+patient,response['total']==sum(d['document_date']['year']==2026 for d in selected))
            response=client.own('records/search/',method='POST',data={'q':'Fictional Comfort Test Clinic'})
            check('facility-search:'+patient,response['total']==len(selected))
            response=client.own('records/search/',method='POST',data={'order':'document_date'})
            observed={r['current_version']['id']:r['metadata']['values']['document_date'] for r in response['records']}
            check('partial-date-components-retained:'+patient,all(observed[state['documents'][d['id']]['version_id']]==d['document_date'] for d in selected))
            medicines=client.own('medications/')['medications']
            uses={m['values']['use_status'] for m in medicines}
            check('prescription-not-assumed-use:'+patient,'reported_prescribed' in uses and 'reported_taken' not in uses)
            if patient=='P15':check('later-reported-non-use-retained','not_taken' in uses)
        for patient,query in [('P02','diabet'),('P13','EVAL-OLDER-000')]:
            if patient not in clients:continue
            response=clients[patient].own('records/search/',method='POST',data={'q':query})
            check('extracted-text-search:'+patient,response['total']>0)
        if 'P10' in clients:
            client=clients['P10'];doctors=client.own('care/practitioners/')['items'];assignments=client.own('care/assignments/')['items']
            check('distinct-reported-provider-facilities',len({d['values']['facility'] for d in doctors})>=2)
            check('current-and-historical-provider-links',{'current','historical'}<={a['values']['participation'] for a in assignments})
            check('provider-labels-not-acting-contexts',len(client.data['contexts'])==1 and client.data['contexts'][0]['capacity']=='Self')
            if 'A02' in clients:
                bundle=packet(client,state,'multiple-providers-P10',['P10-B-01','P10-B-04'],suite)
                grant=client.own('grants/',method='POST',data={'kind':'read','target_id':bundle['revision_id'],
                  'recipient_id':clients['A02'].user,'purpose':VERSION+' multi-provider consultation','expires_in_minutes':10},expected=(201,))
                shared=clients['A02'].call('/api/continuity/shares/'+grant['id']+'/')
                check('multiple-provider-packet-exact-selected-sources',
                  {i['source_version_id'] for i in shared['items']}=={state['documents'][k]['version_id'] for k in ('P10-B-01','P10-B-04')})
                check('multiple-provider-recipient-own-context-retained',len(clients['A02'].data['contexts'])==1 and clients['A02'].workspace!=client.workspace)
                client.own('grants/read/'+grant['id']+'/revoke/',method='POST',data={})
                response=clients['A02'].call('/api/continuity/shares/'+grant['id']+'/',expected=(404,),raw=True)
                check('multiple-provider-share-revocation',response.status_code==404)
        value={'profile':profile,'category':'deterministic_journeys','checks':checks,'passed':all(c['passed'] for c in checks),
          'patient_review_is_not_model_accuracy':True,'human_usability_validation':False}
        write_json(RUNTIME/f'journeys-{profile}.json',value);return {'checks':len(checks),'passed':value['passed']}
    finally:
        for client in clients.values():client.close()


def dispatch(ids,kind,mode):
    if not ids:return []
    output=env.compose('run','--rm','--no-deps','worker','python','src/manage.py','ecosystem_jobs','--mode',mode,
        '--kind',kind,'--limit',str(len(ids)),'--ids',*ids)
    rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    results=rows[-1]['results']
    path=RUNTIME/('dispatch-'+kind+'.json')
    receipt=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'results':[]}
    receipt['results']+=results;write_json(path,receipt)
    return results


@env.exclusive
def process(profile,live=False,max_jobs=16):
    env.guard();suite=run.load();state=run.ledger();patients,actors,docs=run.selected(suite,profile)
    keys={p['id'] for p in patients+actors};clients=clients_for(keys,state);jobs=[];job_docs={}
    try:
        accepted=next((r for r in state['operations'].get('P07:contribution-flow',[]) if r['state']=='accepted'),None)
        if accepted and 'P07-accepted-AUX' not in state['documents'] and 'P07' in clients:
            rows=clients['P07'].own('records/search/',method='POST',data={'q':'P07-accepted-AUX'})['records']
            matches=[r for r in rows if r['current_version']['id']==accepted['accepted_source_id']]
            if len(matches)!=1:raise ValueError('Accepted fixture source cannot be resolved safely')
            row=matches[0];version=row['current_version']
            state['documents']['P07-accepted-AUX']={'workspace_id':clients['P07'].workspace,'record_id':row['id'],
              'version_id':version['id'],'sha256':version['sha256'],'origin':'accepted_contribution','upload_seconds':None}
            run.persist(state)
        docs=docs+[d for d in suite['auxiliary_documents'] if d['id'] in state['documents'] and d['patient'] in keys]
        if live:
            target_keys=['P01-X-001','P01-X-002','P15-X-008','P15-X-009']
            docs=[d for d in docs if d['id'] in target_keys]
        for doc in docs:
            receipt=state['documents'].get(doc['id'])
            if not receipt: continue
            record=clients[doc['patient']].own(f"records/{receipt['record_id']}/")
            job=record['jobs'][0]
            if job['state'] in (['queued','waiting_model'] if live else ['queued']):
                jobs.append(job['id']);job_docs[job['id']]=doc['id']
            if len(jobs)>=max_jobs:break
        results=dispatch(jobs,'record','live' if live else 'extract')
        path=RUNTIME/('processing-live.json' if live else 'processing-extract.json')
        existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'results':[]}
        for item in results:item['fixture']=job_docs[item['id']]
        existing['results']+=results;write_json(path,existing)
        return {'profile':profile,'mode':'live' if live else 'extract','processed':len(results),
          'states':{s:sum(r['state']==s for r in results) for s in sorted({r['state'] for r in results})}}
    finally:
        for client in clients.values():client.close()


def retrieval_scores(expected,actual):
    expected=set(expected);actual=list(dict.fromkeys(actual))[:5];hits=len(expected.intersection(actual))
    return {'recall_at_5':hits/len(expected) if expected else None,'precision_at_5':hits/5,
        'returned_precision':hits/len(actual) if actual else None,
        'reciprocal_rank':next((1/(i+1) for i,k in enumerate(actual) if k in expected),0) if expected else None,
        'correct_abstention':not actual if not expected else None}


def runtime_failure_gate(result):
    failures=[]
    for key,case in result['cases'].items():
        task=case.get('task',{});config=task.get('configuration',{})
        timeout=config.get('request_timeout_seconds',0)
        # Failed production tasks intentionally leave latency_seconds null.
        # Dispatch wall time is diagnostic evidence, not successful-response latency.
        elapsed=task.get('latency_seconds') or case.get('dispatch_elapsed_seconds') or 0
        if (task.get('state')=='failed' and task.get('error_code')=='model_access_failed'
            and config.get('base_url')=='http://inference:8080/v1' and timeout>0
            and elapsed>=.95*timeout):failures.append(key)
    path=RUNTIME/'runtime-gate.json'
    if len(failures)>=2 and not path.exists():
        write_json(path,{'active':True,'reason':'Repeated local access failures with dispatch wall time near configured timeout; review runtime before larger cases',
          'failed_cases':failures,'compact_single_source_controls_permitted':True})


@env.exclusive
def evaluate(profile,live=False,max_jobs=16,case_ids=None):
    env.guard();suite=run.load();cases=case_manifest(suite);state=run.ledger();people,_,selected=run.selected(suite,profile)
    eligible={p['id'] for p in people};selected_ids={d['id'] for d in selected}
    selected_ids.update(d['id'] for d in suite['auxiliary_documents'] if d['patient'] in eligible and d['id'] in state['documents'])
    clients=clients_for(eligible,state)
    path=RUNTIME/f'evaluation-{profile}.json'
    result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':cases['version'],'profile':profile,
      'population_sha256':cases['population_sha256'],'evaluation_sha256':sha((PUBLIC/'evaluation-v8.json').read_bytes()),'cases':{},
      'human_semantic_review':{'status':'pending','clinician_involvement':False},'actual_usability':{'status':'not_performed'}}
    calls=0;reverse={r['version_id']:key for key,r in state['documents'].items()}
    try:
        runtime_failure_gate(result)
        if result['version']!=cases['version']:
            old_version=result['version'].rsplit('-',1)[-1]
            archive=RUNTIME/f'evaluation-{profile}-{old_version}.json'
            if not archive.exists():write_json(archive,result)
            result.update(version=cases['version'],evaluation_sha256=sha((PUBLIC/'evaluation-v8.json').read_bytes()),
              continued_from_result_sha256=sha(archive.read_bytes()))
        order=['cpu4-co01','cpu3-o01','cpu3-co01','cpu3-o02','cpu2-o01','cpu2-q08','cpu2-co01','cpu-q01','cpu-o01','cpu-q08','cpu-co01','cpu-co02','cpu-q06','cq01','co01','co02','q01','o01','q08','o02','q06','o03','q07','o04','q02','o05','q04','q05','q03']
        execution=sorted(cases['cases'],key=lambda c:-1 if c['kind']=='metadata' else order.index(c['id']))
        if case_ids:
            if set(case_ids)-{c['id'] for c in execution}:raise ValueError('Unknown evaluation case ID')
            execution=[c for c in execution if c['id'] in case_ids]
        for case in execution:
            key=case['id'];patient=case['patient']
            if patient not in eligible or any(d not in selected_ids for d in case.get('sources',[])):continue
            client=clients[patient]
            prior=result['cases'].get(key,{})
            prior.update(kind=case['kind'],patient=patient)
            if case['kind']=='metadata':
                doc=next(d for d in suite['documents'] if d['id']==case['sources'][0]);receipt=state['documents'].get(doc['id'])
                if not receipt:continue
                record=client.own(f"records/{receipt['record_id']}/");proposals=record['proposals']
                outcome={'kind':'metadata','patient':patient,'software_job':record['jobs'][0],
                  'expected':case['expected'],'independent_reference':True,'patient_review_is_not_model_ground_truth':True}
                processing=RUNTIME/'processing-live.json'
                attempts=json.loads(processing.read_text(encoding='utf-8'))['results'] if processing.exists() else []
                outcome['attempts']=[r for r in attempts if r.get('fixture')==doc['id']]
                outcome['model_attempted']=bool(outcome['attempts'])
                if proposals:
                    prediction=proposals[0]['values'];outcome['prediction']=prediction
                    outcome['prompt_version']=proposals[0]['prompt_version']
                    outcome['schema_and_source_quotes_valid']=True
                    outcome['field_correct']={f:prediction.get(f)==v for f,v in case['expected'].items()}
                else:outcome.update(schema_and_source_quotes_valid=False if outcome['model_attempted'] else None,field_correct=None)
                result['cases'][key]=outcome;write_json(path,result);continue
            expected=[d for d in case.get('relevant',[]) if d in selected_ids]
            if case['kind']=='search':
                baseline=client.own('records/search/',method='POST',data={'q':case['query']})
                actual=[reverse.get(r['current_version']['id'],'unmapped') for r in baseline['records']]
                prior.update(kind='search',patient=patient,baseline_literal_keyword=retrieval_scores(expected,actual),
                    expected_relevant=expected,unpopulated_reference_sources=[d for d in case['relevant'] if d not in selected_ids])
            if not live:
                result['cases'][key]=prior;write_json(path,result);continue
            task=None
            if prior.get('task'):
                task=client.own('assistant/tasks/'+prior['task']['id']+'/')
                prior['task']=task
                if task['state']=='processing':
                    result['cases'][key]=prior;write_json(path,result);continue
                if task['state'] not in ('queued','waiting_model') and 'schema_and_source_quotes_valid' in prior:continue
            if task is None:
                if calls>=max_jobs:continue
                gate=RUNTIME/'runtime-gate.json'
                if gate.exists() and json.loads(gate.read_text(encoding='utf-8')).get('active') and case.get('scope') not in ('compact_control','local_cpu_followup','local_cpu_v2_followup','local_cpu_v3_followup','local_cpu_v4_followup'):
                    prior['not_run_reason']='repeated local request timeouts; larger contexts gated pending runtime review'
                    result['cases'][key]=prior;write_json(path,result);continue
                prior.pop('not_run_reason',None)
                if case['kind']=='search': parameters={'query':case['query']}
                else: parameters={'packet_id':packet(client,state,key,case['sources'],suite)['id']}
                task=client.own('assistant/tasks/',method='POST',data={'kind':case['kind'],'parameters':parameters},expected=(202,))
                prior['task']=task;result['cases'][key]=prior;write_json(path,result)
            if task['state'] in ('queued','waiting_model'):
                if calls>=max_jobs:
                    prior['task']=task;result['cases'][key]=prior;write_json(path,result);continue
                before=time.perf_counter();dispatch([task['id']],'assistant','live');calls+=1
                prior['dispatch_elapsed_seconds']=time.perf_counter()-before
            task=client.own('assistant/tasks/'+task['id']+'/');prior['task']=task
            prior['schema_and_source_quotes_valid']=task['state']=='completed'
            prior['scope']=case.get('scope','functional_case')
            prior['clinical_semantic_validity']='not_established'
            included=[reverse.get(s['source_version_id'],'unmapped') for s in task['sources']]
            if case['kind']=='search':
                matches=[reverse.get(m['source_version_id'],'unmapped') for m in (task.get('result') or {}).get('matches',[])]
                prior['model_retrieval']=retrieval_scores(expected,matches) if task['state']=='completed' else None
                prior['expected_sources_in_preselection']={d:d in included for d in expected}
                prior['retrieval_stage_excluded_expected']=[d for d in expected if d not in included]
                prior['included_context_count']=len(included)
            else:
                text='\n'.join(i['text'] for i in (task.get('result') or {}).get('items',[])).casefold()
                prior['required_phrase_screens']=[any(p.casefold() in text for p in group) for group in case['required_any']] if task['state']=='completed' else None
                prior['forbidden_phrase_flags']=[p for p in case['forbidden'] if p.casefold() in text] if task['state']=='completed' else None
                prior['human_review_required']=True
            result['cases'][key]=prior;write_json(path,result)
            runtime_failure_gate(result)
            print(json.dumps({'case':key,'state':task['state'],'model_call_count':calls}),flush=True)
        return {'profile':profile,'model_calls_this_invocation':calls,'saved_cases':len(result['cases']),'human_review':'pending'}
    finally:
        for client in clients.values():client.close()


@env.exclusive
def report(profile,live=False,max_jobs=16):
    from .reporting import build
    return build(profile,run.load(),run.ledger())
