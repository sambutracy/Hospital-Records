"""Extract explicitly bound fictional records without filling the CPU model queue."""
import json
import uuid
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from identity.models import OIDCIdentity
from records.models import IngestionJob, MetadataHead
from records.worker import process_one

ISSUER='http://localhost:8081/realms/continuity'


def validate_bindings(value):
    if value.get('version')!='comfort-ecosystem-v1' or value.get('issuer')!=ISSUER:
        raise CommandError('Wrong client-demo installation')
    rows=value.get('documents',[])
    if len(rows)>308 or not value.get('accounts'):
        raise CommandError('Explicit bounded client-demo bindings required')
    owners={a['workspace_id']:a for a in value['accounts']}
    for row in rows:
        owner=owners.get(row['workspace_id'])
        if not owner or not owner['username'].startswith('ecosystem.'):
            raise CommandError('Document owner is not a bound fixture account')
    return rows,owners


class Command(BaseCommand):
    help='Local demo only: prepare bound fixture PDF text with no model generation.'

    def add_arguments(self,parser):
        parser.add_argument('--bindings',required=True)

    def handle(self,*args,**options):
        if not settings.DEMO_MODE or settings.OIDC_ISSUER!=ISSUER:
            raise CommandError('Ordinary localhost demo installation required')
        value=json.loads(Path(options['bindings']).read_text(encoding='utf-8'))
        rows,owners=validate_bindings(value)
        results=[]
        for row in rows:
            owner=owners[row['workspace_id']]
            with transaction.atomic():
                job=IngestionJob.objects.select_for_update(of=('self',)).select_related('requested_by','source_version').get(
                    source_version_id=row['version_id'],workspace_id=row['workspace_id'],attempt_number=1)
                if (str(job.requested_by_id)!=owner['user_id'] or job.source_version.sha256!=row['sha256']
                    or str(job.source_version.record_id)!=row['record_id']
                    or not OIDCIdentity.objects.filter(user=job.requested_by,issuer=ISSUER,subject=owner['subject']).exists()):
                    raise CommandError('Exact fixture identity/source binding required')
                if not MetadataHead.objects.filter(source_version=job.source_version,revision__gt=0).exists():
                    raise CommandError('Review fixture metadata through the normal API first')
                if job.state!='queued':
                    results.append({'id':str(job.pk),'state':job.state,'skipped':True});continue
                job.state='processing';job.lease_token=uuid.uuid4();job.started_at=timezone.now()
                job.lease_expires_at=timezone.now()+timedelta(seconds=180)
                job.save(update_fields=['state','lease_token','started_at','lease_expires_at'])
            result=process_one(job.pk,job.lease_token,extract_only=True)
            results.append({'id':str(job.pk),'state':result})
        self.stdout.write(json.dumps({'model_calls':0,'results':results}))
