"""Test-stack-only bounded dispatch through the existing production worker functions."""
import hashlib
import json
import os
import time
import uuid
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from records.models import AssistantTask, IngestionJob, GenerationRun, TextExtraction
from records import worker, assistant_worker

VERSION='comfort-ecosystem-v1'


def check_fixture_sources(job,kind,suite):
    fixture_hashes={d['sha256'] for d in suite['documents']+suite.get('auxiliary_documents',[])}
    hashes=([job.source_version.sha256] if kind=='record' else
        list(job.sources.values_list('source_version__sha256',flat=True)))
    if not hashes or not set(hashes)<=fixture_hashes:raise CommandError('Non-fixture source bytes rejected')


class Command(BaseCommand):
    help='Bounded synthetic evaluation dispatch; unavailable in the ordinary application stack.'
    def add_arguments(self,parser):
        parser.add_argument('--mode',choices=['inspect','extract','live'],required=True)
        parser.add_argument('--kind',choices=['record','assistant'],default='record')
        parser.add_argument('--ids',nargs='*',default=[])
        parser.add_argument('--limit',type=int,default=1)
    def handle(self,*args,**options):
        manifest=Path('/ecosystem/population.json')
        if not settings.DEMO_MODE or os.environ.get('COMFORT_SYNTHETIC_ECOSYSTEM')!=VERSION or not manifest.is_file():
            raise CommandError('Dedicated synthetic stack required')
        suite=json.loads(manifest.read_text(encoding='utf-8'))
        if suite.get('version')!=VERSION or suite.get('synthetic_only') is not True: raise CommandError('Wrong fixture manifest')
        if options['mode']=='inspect':
            self.stdout.write(json.dumps({'environment':VERSION,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}));return
        if not 1<=options['limit']<=32 or len(options['ids'])>32: raise CommandError('Explicit bounded batch required')
        if not options['ids']: raise CommandError('Select explicit fixture job IDs')
        bindings=Path('/ecosystem-runtime/accounts.private.json')
        if not bindings.is_file(): raise CommandError('Exact fixture identity bindings required')
        accounts=json.loads(bindings.read_text(encoding='utf-8'))
        subjects={entry['keycloak_subject'] for entry in accounts.values() if entry.get('keycloak_subject')}
        if options['mode']=='extract':
            if options['kind']!='record': raise CommandError('Extraction applies only to record jobs')
            # The normal worker extracts and persists text, then reports waiting_model
            # when configuration is unavailable. No fabricated extraction rows/states.
            for name in ('LLM_NAME','LLM_BASE_URL','LLM_API_KEY','LLM_API_KEY_FILE'): os.environ[name]=''
        model=IngestionJob if options['kind']=='record' else AssistantTask
        results=[]
        for job_id in options['ids'][:options['limit']]:
            with transaction.atomic():
                job=model.objects.select_for_update().select_related('requested_by').get(pk=uuid.UUID(job_id))
                # Use the actual configured issuer and dataset marker in account names;
                # identities are established by the application's verified code flow.
                if not job.requested_by.person.display_name.startswith('Synthetic '): raise CommandError('Non-fixture job rejected')
                from identity.models import OIDCIdentity
                bound=OIDCIdentity.objects.filter(user=job.requested_by,issuer=settings.OIDC_ISSUER,subject__in=subjects).exists()
                if not bound or ':8091/' not in settings.OIDC_ISSUER: raise CommandError('Wrong synthetic issuer')
                check_fixture_sources(job,options['kind'],suite)
                allowed=['queued','waiting_model'] if options['mode']=='live' else ['queued']
                if job.state not in allowed:
                    results.append({'id':str(job.pk),'state':job.state,'skipped':True});continue
                job.state='processing';job.lease_token=uuid.uuid4();job.started_at=timezone.now();job.finished_at=None
                job.lease_expires_at=timezone.now()+timedelta(seconds=420)
                job.save(update_fields=['state','lease_token','started_at','finished_at','lease_expires_at'])
            started=time.perf_counter()
            try:
                process=subprocess.run([sys.executable,str(settings.BASE_DIR/'manage.py'),
                    'ecosystem_capture',options['kind'],str(job.pk),str(job.lease_token)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=360)
                if process.returncode:
                    (worker.finish_failure if options['kind']=='record' else assistant_worker.finish_failure)(job.pk,job.lease_token,'worker_process_failed')
            except subprocess.TimeoutExpired:
                (worker.finish_failure if options['kind']=='record' else assistant_worker.finish_failure)(job.pk,job.lease_token,'processing_timeout')
            job.refresh_from_db()
            row={'id':str(job.pk),'state':job.state,'safe_error_code':job.safe_error_code,'elapsed_seconds':time.perf_counter()-started,
                'queue_wait_seconds':max(0,(job.started_at-job.created_at).total_seconds()),
                'mode':options['mode'],'kind':options['kind']}
            if options['kind']=='record':
                extraction=TextExtraction.objects.filter(source_version=job.source_version).first()
                run=GenerationRun.objects.filter(job=job).first()
                row['text_extraction_present']=extraction is not None
                row['extraction_delay_seconds']=max(0,(extraction.created_at-job.started_at).total_seconds()) if extraction else None
                if run:
                    row.update(model=run.model_name,configuration=run.configuration,usage=run.usage,
                        generation_seconds=(run.finished_at-run.created_at).total_seconds() if run.finished_at else None)
            else:
                row.update(model=job.model_name,configuration=job.configuration,usage=job.usage,coverage=job.coverage,
                    generation_seconds=job.latency_seconds)
            results.append(row)
            self.stdout.write(json.dumps({'progress':len(results),'selected':min(len(options['ids']),options['limit'])}),ending='\n')
        self.stdout.write(json.dumps({'environment':VERSION,'results':results}))
