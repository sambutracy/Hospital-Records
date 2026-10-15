"""Versioned fictional Journal fixtures through normal localhost OIDC/CSRF APIs."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ecosystem.client import Client
from ecosystem.client_demo import LOCAL
from ecosystem.prepare import ROOT, sha, write_json


def seed():
    manifest_path=ROOT/'data/journal-v1/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    receipt=ROOT/'.runtime/journal-demo/receipt.private.json'
    state=json.loads(receipt.read_text()) if receipt.exists() else {
        'version':manifest['version'],'manifest_sha256':sha(manifest_path.read_bytes()),'app':LOCAL.APP,'entries':{}}
    if state.get('manifest_sha256')!=sha(manifest_path.read_bytes()) or state.get('app')!=LOCAL.APP:
        raise ValueError('Journal receipt or manifest changed; use a new version.')
    accounts=LOCAL.accounts()
    if not all(key in accounts for key in (manifest['patient'],manifest['empty_patient'])):
        raise ValueError('Prepare the existing client-demo accounts first; no identities are recreated here.')
    client=Client(accounts[manifest['patient']],LOCAL).sign_in()
    try:
        current=client.own('journal/draft/')['draft']
        if current: raise ValueError('A patient recovery draft exists. Resolve it in Comfort before seeding.')
        concerns=client.own('care/concerns/')['items']
        matches=[item for item in concerns if item['values']['title']==manifest['concern'] and item['status']=='active']
        if 'concern_id' not in state:
            if matches: state['concern_id']=matches[0]['id']
            else:
                item=client.own('care/concerns/',method='POST',expected=(201,),data={'expected_revision':0,'values':{
                    'title':manifest['concern'],'description':'Authored fictional observations for Journal testing; not a diagnosis.',
                    'kind':'investigation','certainty':'unconfirmed','onset':{'precision':'unknown','year':None,'month':None,'day':None}}})
                state['concern_id']=item['id']
            write_json(receipt,state)
        for entry in manifest['entries']:
            previous=state['entries'].get(entry['id'])
            if previous:
                if previous.get('state')!='saved': raise ValueError('An earlier write has an uncertain outcome; inspect its private receipt before retrying.')
                client.own('journal/'+previous['event_id']+'/')
                continue
            state['entries'][entry['id']]={'state':'pending'};write_json(receipt,state)
            values={key:value for key,value in entry.items() if key!='id'}
            values['concern_id']=state['concern_id']
            result=client.own('journal/',method='POST',expected=(201,),data={'values':values,'expected_revision':0,'draft_revision':None})
            state['entries'][entry['id']]={'state':'saved','event_id':result['id'],'revision':result['revision']}
            write_json(receipt,state)
        state['workspace_id']=client.workspace
    finally: client.close()
    empty=Client(accounts[manifest['empty_patient']],LOCAL).sign_in()
    try:
        rows=empty.own('journal/?from=2026-01-01&to=2026-12-31&undated=true')['items']
        state['empty_patient_observed_entries']=len(rows)
    finally: empty.close()
    write_json(receipt,state)
    return {'version':state['version'],'saved_entries':len(state['entries']),
        'workspace_id':state['workspace_id'],'empty_patient_observed_entries':state['empty_patient_observed_entries']}


if __name__=='__main__': print(json.dumps(seed()))
