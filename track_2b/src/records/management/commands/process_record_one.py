from django.core.management.base import BaseCommand
from records.worker import process_one


class Command(BaseCommand):
    help='Process one claimed record job; invoked by the isolated worker.'
    def add_arguments(self,parser):
        parser.add_argument('job_id')
        parser.add_argument('lease_token')
    def handle(self,*args,**options):
        self.stdout.write(process_one(options['job_id'],options['lease_token']))
