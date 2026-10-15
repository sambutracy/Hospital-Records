"""Explicitly populate the ordinary local app for hands-on browser testing.

Separate receipts and OIDC subjects preserve the frozen evaluation installation.
Only fixture accounts are created; all records/profile writes use normal APIs.
No grants are pre-approved: the tester exercises consent in the client.
"""
import json
from pathlib import Path
from . import environment, prepare, run
from .client import Client, provision

DIRECTORY=prepare.ROOT/'.runtime/client-demo'


class LocalEnvironment:
    APP='http://localhost:8000'
    KEYCLOAK='http://localhost:8081'

    def credentials(self):
        return dict(line.split('=',1) for line in (prepare.ROOT/'.env').read_text().splitlines()
                    if '=' in line and not line.startswith('#'))

    def accounts(self):
        path=DIRECTORY/'accounts.private.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def save_accounts(self,value):
        path=DIRECTORY/'accounts.private.json'
        prepare.write_json(path,value);path.chmod(0o600)


LOCAL=LocalEnvironment()


def save(state):
    prepare.write_json(DIRECTORY/'state.private.json',state)


def load_state():
    path=DIRECTORY/'state.private.json'
    digest=prepare.sha((prepare.PUBLIC/'population.json').read_bytes())
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'version':prepare.VERSION,'app':LOCAL.APP,'keycloak':LOCAL.KEYCLOAK,
        'population_sha256':digest,'accounts':{},'documents':{},'operations':{}}
    if any(state.get(k)!=v for k,v in {
        'version':prepare.VERSION,'app':LOCAL.APP,'keycloak':LOCAL.KEYCLOAK,'population_sha256':digest}.items()):
        raise ValueError('Client-demo receipt belongs to another installation or population')
    return state


def initialize_accounts(people):
    if LOCAL.accounts():return provision(people,LOCAL)
    # Keep the previously given fictional passwords convenient, but never copy
    # another realm's OIDC subjects or its record/workspace/grant IDs.
    old=environment.accounts()
    known={}
    for person in people:
        previous=old.get(person['id'])
        if previous and previous['username']!=person['account']:
            raise ValueError('Fixture username differs; no account was adopted')
        if previous:known[person['id']]={k:previous[k] for k in ('username','password')}
    LOCAL.save_accounts(known)
    return provision(people,LOCAL)


def create_once(client,state,key,suffix,field,items_key,values):
    if key in state['operations']:return
    rows=client.own(suffix)[items_key]
    matches=[row for row in rows if row.get('values',row).get(field)==values[field]]
    if len(matches)>1:raise ValueError('Ambiguous saved client-demo operation')
    result=matches[0] if matches else client.own(suffix,method='POST',
        data={'values':values,'expected_revision':0},expected=(201,))
    state['operations'][key]=result;save(state)


def enrich(client,person,state):
    key=person['id']
    profile=client.own('profile/')
    if profile['revision']==0:
        values={**profile['values'],'full_name':f'Synthetic {key} - fictional evaluation','preferred_name':f'Synthetic {key}'}
        client.own('profile/',method='POST',data={'values':values,'expected_revision':0})
    for actor in {'P02':['A01','A02'],'P03':['A05','A06'],'P04':['A07','A08']}.get(key,[]):
        create_once(client,state,key+':contact:'+actor,'care-circle/','full_name','contacts',{
            'full_name':f'Synthetic {actor}', 'relationship':'caregiver' if key=='P03' else 'guardian' if key=='P04' else 'clinician',
            'email':'','phone':'','notes':'Fictional reported relationship; no automatic record access or verified authority.',
            'is_next_of_kin':False,'is_emergency_contact':False,'recipient_id':state['accounts'][actor]['user_id']})


def bindings(state,known):
    return {'version':prepare.VERSION,'issuer':LOCAL.KEYCLOAK+'/realms/continuity',
        'accounts':[{**row,'subject':known[key]['keycloak_subject'],'username':known[key]['username']}
                    for key,row in state['accounts'].items()],
        'documents':list(state['documents'].values())}


@environment.exclusive
def seed(max_documents=64):
    if not 1<=max_documents<=64:raise ValueError('Use a bounded batch of at most 64 documents')
    suite=run.load();patients,actors,docs=run.selected(suite,'functional')
    state=load_state();known=initialize_accounts(patients+actors);clients={}
    try:
        for person in patients+actors:
            key=person['id'];client=Client(known[key],LOCAL).sign_in();clients[key]=client
            binding={'user_id':client.user,'workspace_id':client.workspace}
            if key in state['accounts'] and state['accounts'][key]!=binding:
                raise ValueError('Client-demo identity binding changed')
            state['accounts'][key]=binding;save(state)
        count=0
        for doc in docs:
            if doc['id'] in state['documents'] or count>=max_documents:continue
            data=prepare.runtime_path(doc['prepared_path']).read_bytes()
            if prepare.sha(data)!=doc['sha256']:raise ValueError('Prepared source checksum differs')
            client=clients[doc['patient']]
            result=client.own('records/',method='POST',files={'file':(doc['id']+'.pdf',data,'application/pdf')},expected=(200,201))
            version=result['version']
            if version['sha256']!=doc['sha256']:raise ValueError('Uploaded source checksum differs')
            receipt={'fixture_id':doc['id'],'patient':doc['patient'],'workspace_id':client.workspace,
                'record_id':version['record_id'],'version_id':version['id'],'sha256':doc['sha256']}
            state['documents'][doc['id']]=receipt;save(state);count+=1
            if count%16==0:print(json.dumps({'uploaded_this_batch':count,'total':len(state['documents'])}),flush=True)
        # Manually reviewed metadata references are labelled as patient assertions,
        # never as AI outputs. Existing edits and nonzero revisions are preserved.
        for doc in docs:
            if doc['id'] not in state['documents']:continue
            receipt=state['documents'][doc['id']];client=clients[doc['patient']]
            row=client.own(f"records/{receipt['record_id']}/")
            if row['metadata']['revision']==0:
                client.own(f"records/{receipt['record_id']}/review/",method='POST',data={
                    'source_version_id':receipt['version_id'],'expected_revision':0,'values':{
                        'document_type':doc['document_type'],'document_date':doc['document_date'],'facility_name':doc['facility']}})
        for person in patients:enrich(clients[person['id']],person,state)
        prepare.write_json(DIRECTORY/'bindings.private.json',bindings(state,known))
        write_walkthrough(state,suite,known)
        return {'app':LOCAL.APP,'accounts':len(state['accounts']),'new_uploads':count,
                'completed':len(state['documents']),'planned':len(docs),'grants_created':0}
    finally:
        for client in clients.values():client.close()


def write_walkthrough(state,suite,known):
    samples=DIRECTORY/'upload-samples';samples.mkdir(parents=True,exist_ok=True)
    for key in ('P01-X-001','P07-accepted-AUX','P07-rejected-AUX'):
        doc=next(d for d in suite['documents']+suite['auxiliary_documents'] if d['id']==key)
        data=prepare.runtime_path(doc['prepared_path']).read_bytes()
        if prepare.sha(data)!=doc['sha256']:raise ValueError('Upload sample checksum differs')
        target=samples/(key+'.pdf')
        if target.exists() and prepare.sha(target.read_bytes())!=doc['sha256']:
            raise ValueError('Existing upload sample was edited; no overwrite performed')
        if not target.exists():target.write_bytes(data)
    lines=['# Comfort: hands-on client testing','',f'Open {LOCAL.APP}/app/. These accounts now belong to the ordinary local app.',
        'The earlier evaluation at port 8010 is preserved separately; its saved outputs are not copied here.',
        'All people and documents below are fictional. IDs are Comfort account IDs, not national IDs.','',
        '## Accounts','', '| Scenario | Username | Password | Comfort account ID | Records |','|---|---|---|---|---:|']
    for person in suite['patients'][:15]+suite['actors']:
        key=person['id'];account=known[key];binding=state['accounts'][key]
        count=sum(d['patient']==key for d in state['documents'].values())
        label=person.get('scenario',person.get('role_label','Additional test account'))
        lines.append(f"| {key}: {label} | `{account['username']}` | `{account['password']}` | `{binding['user_id']}` | {count} |")
    lines+=['','## What is ready','',
        'Records and their metadata are preloaded through normal authorized APIs. Searchable PDF text is prepared separately. '
        'Metadata is manually reviewed fixture information, not an Apertus result. No sharing consent is pre-approved. '
        'P14 remains empty so you can exercise onboarding. New UI links currently lead to the earlier profile/sharing/recipient screens.',
        '', '## P02: distinguish family history from the patient','',
        'One source describes severe left hip osteoarthritis and a planned total left hip replacement, '
        'with source-reported hypertension, hyperlipidemia, mild osteopenia and mild anaemia (Hb 10.8 g/dL). '
        'It lists paracetamol 500 mg twice daily and ibuprofen 400 mg as needed, and a plan for ferrous sulfate 200 mg daily. '
        'These are historical statements in a synthetic note, not a verified current medication list or diagnosis.',
        'Sign in as ecosystem.p02. Open Records and search `diabetes`. Open the matching original. '
        'The reference passage says “Father had type 2 diabetes and HLD”. This must not become a diagnosis of diabetes for the patient. '
        'Use “Find related records with Apertus” for the same query. It should cite supporting text or abstain; '
        'a search result is not a diagnosis. Exact excerpts may omit nearby qualifications, so read the original.',
        'P02 has intended practitioner recipients A01/A02, not a designated caregiver. '
        'Their account IDs are in the table. Naming a practitioner or saving a contact does not grant access.',
        '', '## P03: patient and caregiver on two browsers','',
        'Use your normal browser for ecosystem.p03 and a second browser/private window for ecosystem.a05. '
        'In P03 Records select one or two originals, enter a visit purpose and create a private visit selection. '
        'In My Care use “Open existing sharing tools”. Under “Approve temporary access”, choose saved contact A05 '
        'or paste their account ID, check the recipient, select “Read an approved packet”, choose the packet, '
        'enter a purpose/expiry, check consent and approve.',
        f"In the A05 browser open {LOCAL.APP}/received/ (or the Received access navigation link). "
        'Refresh and open the received packet. Only selected originals should be readable. '
        'A05 should not gain the full P03 workspace or authority to edit the profile or use patient AI. '
        'Revoke the permission as P03, then refresh A05: further access should be denied. '
        'A06 is a second caregiver for independent-grant tests; A09 is unrelated and should see neither packet.',
        '', '## P07: contributor and patient review','',
        'P07 creates an episode in existing sharing tools and grants A03 “Submit a note to an episode”. '
        'As A03, use Received access to upload a fictional note. That permission alone should not expose patient records. '
        'As P07, review Incoming notes: accept one and reject another. Only the accepted original should join the record library.',
        f'Use the two P07 PDFs in `{samples}` for the contribution test. '
        'The P01-X-001 lab PDF in that same folder can be uploaded as P14’s first record to test normal, live AI metadata extraction.',
        '', '## Apertus questions and checks','',
        '| Account | Action/question | What to check |','|---|---|---|',
        '| P01 | Search `Medicine Q` with Apertus | Source says 5 mg prescribed; whether taken is unknown. Do not report confirmed use. |',
        '| P01 | Select P01-X-001 and P01-X-002, create a visit selection, request an overview | Preserve haemoglobin 12.1 g/dL, specimen 2026-02-27, document dates and medication uncertainty; open citations. |',
        '| P02 | Search `diabetes` with Apertus | Father’s type 2 diabetes/HLD must stay family history; no patient diagnosis inferred. |',
        '| P02 | Search `hip` or `anaemia` with Apertus | Cite the source-reported hip history or Hb 10.8 g/dL; preserve planned procedures versus completed events. |',
        '| P15 | Search `Medicine Z`, then select X-001/X-002/X-007 for an overview | Preserve the 10 mg vs 20 mg source conflict and later “not being taken”; no invented current regimen. |',
        '| P15 | Search `MRI result normal brain` with Apertus | No supplied supporting record: abstain rather than invent a scan result. |',
        '| P13 | Page through the 100 records and search `EVAL-OLDER-000` | Older uploads remain discoverable; inspect bounded model coverage rather than assuming all 100 reached Apertus. |',
        '| P14 | First login, then upload a fictional file | Empty state, upload, persistence after sign-out/sign-in. |',
        '', 'Requests are saved and run serially on the local CPU. Allow minutes, not seconds, and check saved results. '
        'A failed/unsupported answer is a test finding, not a passed case. Images have no automated clinical interpretation. '
        'Voice controls, verified guardian delegation and a new recipient frontend are not implemented.']
    observations=DIRECTORY/'observations.private.json'
    if observations.exists():
        observed=json.loads(observations.read_text(encoding='utf-8'))
        lines+=['','## Observed client test findings','']+['- '+item for item in observed['findings']]
    (DIRECTORY/'CLIENT_TEST_GUIDE.private.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
