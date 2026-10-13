from django.core.management.base import BaseCommand
from records.assistant_worker import process_one


class Command(BaseCommand):
    help='Execute one claimed assistant task without logging source or provider bodies.'
    def add_arguments(self,parser):
        parser.add_argument('task_id')
        parser.add_argument('lease_token')
    def handle(self,*args,**options):
        process_one(options['task_id'],options['lease_token'])
