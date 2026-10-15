"""Private-volume worker liveness; no patient data or queue contents are exposed."""
import json
import time
from pathlib import Path
from django.conf import settings


def path():
    return Path(settings.PRIVATE_STORAGE_ROOT)/'.assistant-worker.json'


def beat(instance,kind,state='running'):
    if kind=='record':return
    target=path();target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+instance+'.tmp')
    temporary.write_text(json.dumps({'instance':instance,'kind':kind,'state':state,'at':time.time()}))
    temporary.replace(target)


def status():
    try:
        value=json.loads(path().read_text())
        available=(value['kind'] in ('all','assistant') and value['state']=='running'
            and 0<=time.time()-value['at']<20)
    except (OSError,ValueError,TypeError,KeyError):available=False
    return {'available':available,'state':'ready' if available else 'unavailable'}
