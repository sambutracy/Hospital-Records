from datetime import timedelta
from pathlib import Path
import subprocess
import sys
import time
import uuid
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from intelligence.trial import TrialError, configuration
from records.models import AssistantTask, IngestionJob
from records.worker import finish_failure
from records.assistant_worker import finish_failure as assistant_failure
from records import worker_health


class Command(BaseCommand):
    help='Serial, bounded background processing; no automatic charged retries.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--kind',choices=['all','assistant','record'],default='all')
    def handle(self,*args,**options):
        self.instance=uuid.uuid4().hex
        self.kind=options['kind']
        self.assistant_burst=0
        try:self.run_loop(options)
        finally:worker_health.beat(self.instance,self.kind,'stopped')

    def run_loop(self,options):
        while True:
            Path('/tmp/records-worker-heartbeat').touch()
            worker_health.beat(self.instance,self.kind)
            now=timezone.now()
            expired=IngestionJob.objects.filter(state='processing',lease_expires_at__lte=now)
            for job in expired:
                finish_failure(job.pk,job.lease_token,'worker_interrupted')
            for task in AssistantTask.objects.filter(state='processing',lease_expires_at__lte=now):
                assistant_failure(task.pk,task.lease_token,'worker_interrupted')
            try:
                config=configuration()
                states=['queued','waiting_model']
                child_timeout=360 if config.get('request_timeout',90)>90 else 150
            except TrialError:
                states=['queued']
                child_timeout=150
            with transaction.atomic():
                record_job=IngestionJob.objects.select_for_update(skip_locked=True).filter(state__in=states).order_by('created_at').first() if self.kind!='assistant' else None
                assistant_job=AssistantTask.objects.select_for_update(skip_locked=True).filter(state__in=states).order_by('created_at').first() if self.kind!='record' else None
                # Interactive requests need not sit behind a bulk upload. Give
                # metadata a turn after at most three assistant requests.
                job=assistant_job if assistant_job is not None and (record_job is None or self.assistant_burst<3) else record_job
                if job:
                    self.assistant_burst=self.assistant_burst+1 if isinstance(job,AssistantTask) else 0
                    job.state='processing'
                    job.lease_token=uuid.uuid4()
                    job.started_at=now
                    job.finished_at=None
                    job.lease_expires_at=now+timedelta(seconds=child_timeout+60)
                    job.save(update_fields=['state','lease_token','started_at','finished_at','lease_expires_at'])
            if job:
                is_assistant=isinstance(job,AssistantTask)
                failure=assistant_failure if is_assistant else finish_failure
                try:
                    process=subprocess.Popen([sys.executable,str(settings.BASE_DIR/'manage.py'),
                        'process_assistant_one' if is_assistant else 'process_record_one',str(job.pk),str(job.lease_token)],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    deadline=time.monotonic()+child_timeout
                    while process.poll() is None:
                        Path('/tmp/records-worker-heartbeat').touch()
                        worker_health.beat(self.instance,self.kind)
                        if time.monotonic()>=deadline:
                            process.kill()
                            process.wait()
                            raise subprocess.TimeoutExpired(process.args,child_timeout)
                        time.sleep(1)
                    if process.returncode:
                        failure(job.pk,job.lease_token,'worker_process_failed')
                except subprocess.TimeoutExpired:
                    failure(job.pk,job.lease_token,'processing_timeout')
                # No child stdout/stderr is logged; it can contain document/parser data.
            if options['once']:
                return
            if not job:
                time.sleep(1)
