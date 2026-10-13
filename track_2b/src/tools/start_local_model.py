"""Start the pinned local Windows text model, preserving app/auth configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[3]
LOCAL=ROOT/'track_2b'/'.runtime'/'local-model'
SERVER=ROOT/'.dev-tools'/'llama-b11429'/'llama-server.exe'
MODEL=LOCAL/'apertus-v1.5-8b-text-q4_k_m.gguf'
MODEL_ID='Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF'
MODEL_SHA='a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--configure-app',action='store_true',help='Change only the three ignored LLM settings after the server is ready.')
    args=parser.parse_args()
    if os.name!='nt' or not SERVER.is_file() or not MODEL.is_file():
        raise SystemExit('Install the documented pinned Windows runner and verified model first.')
    sha=hashlib.sha256()
    with MODEL.open('rb') as source:
        for data in iter(lambda:source.read(8*1024*1024),b''):
            sha.update(data)
    if MODEL.stat().st_size!=5059027136 or sha.hexdigest()!=MODEL_SHA:
        raise SystemExit('Model checksum mismatch; not started.')
    key_file=LOCAL/'server.key'
    if not key_file.exists():
        with key_file.open('x',encoding='utf-8') as output:
            output.write(secrets.token_hex(32)+'\n')
        key_file.chmod(0o600)
    key=key_file.read_text(encoding='utf-8').strip()
    if not key or '\n' in key or '\r' in key:
        raise SystemExit('Invalid local server key file.')
    def ready():
        try:
            request=Request('http://127.0.0.1:9001/v1/models',headers={'Authorization':'Bearer '+key})
            with urlopen(request,timeout=3) as response:
                result=json.loads(response.read(100000))
            return any(item.get('id')==MODEL_ID for item in result.get('data',[]))
        except Exception:
            return False
    if not ready():
        try:
            with socket.create_connection(('127.0.0.1',9001),timeout=1):
                raise SystemExit('Port 9001 is occupied by an unrecognized/unready service; it was not changed.')
        except OSError:
            pass
        command=[str(SERVER),'--model',str(MODEL),'--alias',MODEL_ID,'--host','127.0.0.1','--port','9001',
            '--ctx-size','16384','--parallel','1','--threads','6','--threads-batch','8',
            '--jinja','--chat-template-kwargs',json.dumps({'enable_thinking':False}),
            '--api-key-file',str(key_file),'--no-webui','--log-disable']
        with (LOCAL/'server.stdout.log').open('ab') as out,(LOCAL/'server.stderr.log').open('ab') as err:
            process=subprocess.Popen(command,cwd=SERVER.parent,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        (LOCAL/'server.pid').write_text(str(process.pid)+'\n',encoding='utf-8')
        for _ in range(40):
            if ready():
                break
            if process.poll() is not None:
                raise SystemExit('Local model server exited during startup; inspect private startup logs.')
            time.sleep(2)
        if not ready():
            raise SystemExit('Local server did not become ready; app configuration was not changed.')
    if args.configure_app:
        env=ROOT/'track_2b'/'.env'
        if not env.is_file():
            raise SystemExit('Start the existing application bootstrap first; no identity secrets were created/replaced.')
        replacements={'LLM_NAME':MODEL_ID,'LLM_BASE_URL':'http://host.docker.internal:9001/v1','LLM_API_KEY':key}
        seen=set()
        lines=[]
        for line in env.read_text(encoding='utf-8').splitlines():
            name=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
            if name in replacements:
                if name in seen:
                    raise SystemExit('Duplicate LLM configuration lines; no settings changed.')
                line=name+'='+replacements[name]
                seen.add(name)
            lines.append(line)
        lines.extend(name+'='+value for name,value in replacements.items() if name not in seen)
        env.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (LOCAL/'model-provenance.json').write_text(json.dumps({'model_id':MODEL_ID,
        'repository_revision':'248ec68a63e219e3f061e4c946fc8a20d63b9975','file_sha256':MODEL_SHA,
        'source_checkpoint':'swiss-ai/Apertus-v1.5-8B','conversion_repository':'andreasmartin/apertus-v1.5-8b-text',
        'community_derivative':True,'precision':'Q4_K_M','modalities':['text'],
        'runner_tag':'b11429','runner_commit':'d81235049','context_tokens':16384,
        'parallel_slots':1,'cpu_threads':6,'thinking':False,'listening_host':'127.0.0.1'},indent=2)+'\n',encoding='utf-8')
    print('Local Apertus text server ready on 127.0.0.1:9001; key kept private.')
    if args.configure_app:
        print('Only the three ignored LLM settings were updated. Recreate the worker to load them.')


if __name__=='__main__':
    main()
