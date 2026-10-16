"""Status-only report for explicitly named synthetic verification tasks."""
import json
import uuid
from django.core.management.base import BaseCommand, CommandError
from records.models import AssistantTask


class Command(BaseCommand):
    help='Report safe outcomes/timings for explicit Journal/history/follow-up task IDs; no input, outputs or credentials.'

    def add_arguments(self,parser):
        parser.add_argument('--task-id',action='append',required=True)

    def handle(self,*args,**options):
        results=[]
        for raw in options['task_id']:
            try: ident=uuid.UUID(raw)
            except (TypeError,ValueError): raise CommandError('Invalid task ID.') from None
            task=AssistantTask.objects.filter(pk=ident,kind__in=['journal_interpretation','history_exploration','followup_actions']).first()
            if not task:
                results.append({'task_id':str(ident),'status':'not_found_or_unattempted'}); continue
            results.append({'task_id':str(task.pk),'kind':task.kind,'state':task.state,
                'error_code':task.safe_error_code or None,'model':task.model_name or None,'prompt_version':task.prompt_version or None,
                'valid_result_present':task.state=='completed' and task.result is not None,
                'queue_wait_seconds':(task.started_at-task.created_at).total_seconds() if task.started_at else None,
                'total_worker_seconds':task.latency_seconds,'usage':{key:value for key,value in task.usage.items()
                    if key in ('model_setup_seconds','inference_seconds','validation_seconds','prompt_tokens','completion_tokens','total_tokens','failure_diagnostic',
                        'normalization_method','field_abstentions','discarded_model_fields','source_normalized_fields')}})
        self.stdout.write(json.dumps({'results':results,'note':'Structural workflow evidence only; mock and real runs must be labelled by the operator.'},indent=2))
