"""Private synthetic-only capture around unchanged production worker functions."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from identity.models import OIDCIdentity
from records import worker,assistant_worker
from records.models import IngestionJob,AssistantTask
from intelligence.trial import request_json,redact,TrialError
from ecosystem.prepare import write_json
from .ecosystem_jobs import check_fixture_sources


class Command(BaseCommand):
    def add_arguments(self,parser):
        parser.add_argument('kind',choices=['record','assistant'])
        parser.add_argument('job_id',type=uuid.UUID)
        parser.add_argument('lease_token',type=uuid.UUID)

    def handle(self,*args,**options):
        root=Path('/ecosystem-runtime')
        if (not settings.DEMO_MODE or os.environ.get('COMFORT_SYNTHETIC_ECOSYSTEM')!='comfort-ecosystem-v1'
            or not (root/'accounts.private.json').is_file()):
            raise CommandError('Dedicated synthetic stack required')
        accounts=json.loads((root/'accounts.private.json').read_text(encoding='utf-8'))
        manifest=Path('/ecosystem/population.json')
        if not manifest.is_file():raise CommandError('Fixture manifest required')
        suite=json.loads(manifest.read_text(encoding='utf-8'))
        if suite.get('version')!='comfort-ecosystem-v1' or suite.get('synthetic_only') is not True:
            raise CommandError('Synthetic fixture manifest required')
        model=IngestionJob if options['kind']=='record' else AssistantTask
        job=model.objects.get(pk=options['job_id'])
        subjects=[a['keycloak_subject'] for a in accounts.values() if a.get('keycloak_subject')]
        if (':8091/' not in settings.OIDC_ISSUER or not OIDCIdentity.objects.filter(
            user=job.requested_by,issuer=settings.OIDC_ISSUER,subject__in=subjects).exists()):
            raise CommandError('Exact fixture identity required')
        check_fixture_sources(job,options['kind'],suite)
        module=worker if options['kind']=='record' else assistant_worker
        target=root/'model-captures'/(str(job.pk)+'.json')

        def capture(config,path,payload=None):
            if path!='chat/completions':return request_json(config,path,payload)
            if target.exists():raise ValueError('Model capture is immutable; do not rerun this job')
            value=redact({'request':payload,'response':{},'status':'request_sent'},config['key'])
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('x',encoding='utf-8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2)
            try:
                response=request_json(config,path,payload)
            except Exception as error:
                value.update(status='provider_failed',error_type=type(error).__name__)
                if isinstance(error,TrialError):value['safe_provider_error']=redact(str(error),config['key'])
                value['capture_sha256']=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                write_json(target,value)
                raise
            else:
                # Private fixture-only storage. Never exposes provider authorization
                # headers, cookies or credentials; never changes grading or response.
                value=redact({'request':payload,'response':response,'status':'response_received'},config['key'])
                text=json.dumps(value,ensure_ascii=False,sort_keys=True)
                value['capture_sha256']=hashlib.sha256(text.encode()).hexdigest()
                write_json(target,value)
            return response

        with patch.object(module,'request_json',capture):
            module.process_one(job.pk,options['lease_token'])
