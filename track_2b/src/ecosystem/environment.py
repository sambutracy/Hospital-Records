"""Separate Docker database/Keycloak, loopback host and private resumable credentials."""
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from contextlib import contextmanager
from functools import wraps
from .prepare import ROOT, RUNTIME, PUBLIC, VERSION, write_json, sha

PROJECT='comfort-ecosystem'
APP='http://127.0.0.1:8010'
KEYCLOAK='http://127.0.0.1:8091'


@contextmanager
def operation_lock():
    """One population operation at a time; OS releases this lock after a crash."""
    RUNTIME.mkdir(parents=True,exist_ok=True)
    with (RUNTIME/'operation.lock').open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another synthetic population operation is running; resume after it finishes') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def exclusive(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with operation_lock():return function(*args,**kwargs)
    return wrapped


def docker():
    executable=shutil.which('docker')
    if not executable:
        candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DockerDesktop/resources/bin/docker.exe'
        if candidate.is_file(): executable=str(candidate)
    if not executable: raise ValueError('Docker CLI is required')
    return executable


def compose(*args,capture=True):
    command=[docker(),'compose','--project-name',PROJECT,'--project-directory',str(ROOT),
      '--env-file',str(RUNTIME/'deployment/.env'),'-f',str(ROOT/'compose.yaml'),'-f',str(ROOT/'compose.ecosystem.yaml'),*args]
    result=subprocess.run(command,capture_output=capture,text=True,encoding='utf-8',errors='replace')
    if capture and result.stderr:
        # Private diagnostics are useful for reproducibility; redact generated
        # secrets even though docker build/test normally prints none of them.
        diagnostic=result.stderr
        for key,value in credentials().items():
            if any(term in key for term in ('PASSWORD','SECRET','API_KEY')) and len(value)>8:
                diagnostic=diagnostic.replace(value,'[REDACTED]')
        target=RUNTIME/'compose-logs'/f'{time.time_ns()}.log'
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(diagnostic,encoding='utf-8')
    if result.returncode: raise RuntimeError('Synthetic Compose operation failed; inspect container state (no credentials logged).')
    return result.stdout if capture else ''


def initialize():
    manifest=json.loads((PUBLIC/'population.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=VERSION or manifest.get('synthetic_only') is not True: raise ValueError('Prepare the synthetic manifest first')
    deployment=RUNTIME/'deployment'; marker=deployment/'environment.json'
    if marker.exists():
        value=json.loads(marker.read_text(encoding='utf-8'))
        if value!={'version':VERSION,'project':PROJECT,'app':APP,'keycloak':KEYCLOAK}: raise ValueError('Synthetic marker mismatch')
        return
    if (deployment/'.env').exists(): raise ValueError('Partial configuration: recover it; never replace credentials')
    deployment.mkdir(parents=True,exist_ok=True)
    target=deployment/'src/keycloak';target.mkdir(parents=True,exist_ok=True)
    realm=json.loads((ROOT/'src/keycloak/realm.template.json').read_text(encoding='utf-8'))
    realm['users']=[];realm['displayName']='Comfort synthetic evaluation - fictional users only'
    (target/'realm.template.json').write_text(json.dumps(realm),encoding='utf-8')
    from tools.bootstrap_demo import initialize as bootstrap
    previous={k:os.environ.get(k) for k in ('APP_HOST','APP_PORT','KEYCLOAK_PORT')}
    try:
        os.environ.update(APP_HOST='127.0.0.1',APP_PORT='8010',KEYCLOAK_PORT='8091');bootstrap(deployment)
    finally:
        for key,value in previous.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
    with (deployment/'.env').open('a') as handle: handle.write('\nCOMFORT_SYNTHETIC_ECOSYSTEM='+VERSION+'\n')
    write_json(marker,{'version':VERSION,'project':PROJECT,'app':APP,'keycloak':KEYCLOAK})


def guard():
    marker=RUNTIME/'deployment/environment.json'
    if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!={'version':VERSION,'project':PROJECT,'app':APP,'keycloak':KEYCLOAK}:
        raise ValueError('Dedicated synthetic environment is required')
    result=json.loads(compose('exec','-T','app','python','src/manage.py','ecosystem_jobs','--mode','inspect'))
    if result.get('environment')!=VERSION or result.get('manifest_sha256')!=sha((PUBLIC/'population.json').read_bytes()):
        raise ValueError('Server environment or pinned population differs')
    return result


def credentials():
    values={}
    for line in (RUNTIME/'deployment/.env').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1);values[k]=v
    return values


def accounts():
    path=RUNTIME/'accounts.private.json'
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    return {}


def save_accounts(value):
    path=RUNTIME/'accounts.private.json';write_json(path,value);path.chmod(0o600)
