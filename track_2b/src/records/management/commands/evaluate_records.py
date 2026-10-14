from django.core.management.base import BaseCommand, CommandError
from intelligence.benchmark import run
from intelligence.trial import TrialError


class Command(BaseCommand):
    help = 'Evaluate only the frozen authored synthetic corpus; no patient DB access.'
    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true')
        parser.add_argument('--cases', nargs='+')
        parser.add_argument('--output')
        parser.add_argument('--request-timeout',type=int,default=600,choices=range(90,901),metavar='SECONDS')
    def handle(self, *args, **options):
        try:
            run(live=options['live'], case_ids=options['cases'], output=options['output'],request_timeout=options['request_timeout'])
        except (ValueError, TrialError) as error:
            raise CommandError(str(error)) from None
