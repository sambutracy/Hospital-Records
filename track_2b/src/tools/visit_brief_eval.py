"""Run the separate fictional visit-brief baseline or explicit Apertus cases."""
import argparse
import json
from pathlib import Path
import sys


SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))


def setup_synthetic_runtime():
    """Load model declarations with no application DB or secret configuration."""
    from django.conf import settings
    if not settings.configured:
        settings.configure(SECRET_KEY='fictional-visit-brief-evaluator-only',
            INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'identity', 'records'],
            DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3', 'NAME':':memory:'}},
            AUTH_USER_MODEL='identity.User', DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
            USE_TZ=True, TIME_ZONE='UTC')
    import django
    django.setup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--baseline', action='store_true',
                      help='Deterministic area-hint baseline (the default); makes no model request.')
    mode.add_argument('--live', action='store_true',
                      help='Make one authenticated request per selected fictional case; no retries.')
    parser.add_argument('--case-ids', nargs='+', metavar='CASE_ID',
                        help='Select cases, for example --live --case-ids visit-01.')
    parser.add_argument('--check', action='store_true', help='Validate the separate fixture only.')
    args = parser.parse_args(argv)
    from intelligence.visit_brief_benchmark import load_fixture
    try:
        suite, checksum = load_fixture()
        if args.check:
            print(json.dumps({'version':suite['version'], 'sha256':checksum,
                              'cases':[case['id'] for case in suite['cases']], 'synthetic_only':True}, indent=2))
            return 0
        setup_synthetic_runtime()
        from intelligence.visit_brief_benchmark import run
        path, report = run(live=args.live, case_ids=args.case_ids)
        print('Saved fictional visit-brief evaluation: ' + str(path))
        print(json.dumps({'mode':report['mode'], **report['summary']}, indent=2))
        return 0 if not (report['summary']['invalid_outputs'] or report['summary']['request_failures']
                         or report['summary']['preflight_failures']) else 1
    except (OSError, ValueError, ImportError):
        # Do not echo provider bodies, environment values or exception strings.
        print('Visit-brief evaluation unavailable: check installation, fixture and production planner.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
