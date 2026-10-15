"""Bounded local container resource sampling; no source or credential capture."""
import json
import subprocess
import time
from .environment import docker
from .prepare import RUNTIME


def sample(count=60,interval=30,phase='baseline'):
    if not 1<=count<=120 or not 10<=interval<=60:raise ValueError('Use bounded resource sampling')
    if phase not in ('baseline','cpu-followup-v1','cpu-followup-v2','cpu-followup-v3'):raise ValueError('Unknown measurement phase')
    path=RUNTIME/'resource-samples.jsonl';stop=RUNTIME/('resource-stop' if phase=='baseline' else 'resource-stop-'+phase)
    for index in range(count):
        if stop.exists():break
        result=subprocess.run([docker(),'stats','--no-stream','--format','{{json .}}'],
            capture_output=True,text=True,timeout=20)
        if result.returncode:break
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        rows=[{k:r[k] for k in ('Name','CPUPerc','MemUsage','PIDs')} for r in rows
            if 'inference' in r.get('Name','') or 'comfort-ecosystem-worker' in r.get('Name','')]
        with path.open('a',encoding='utf-8') as handle:
            handle.write(json.dumps({'sample':index,'phase':phase,'unix_time':time.time(),'containers':rows})+'\n')
        time.sleep(interval)
    return {'resource_samples_file':str(path)}
