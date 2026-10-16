"""Reproducible, synthetic-only evaluation for AI-assisted Journal proposals."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src'
sys.path.insert(0, str(SOURCE))
from intelligence.trial import TrialError, configuration

FIXTURE = ROOT / 'data' / 'journal-ai-v1' / 'manifest.json'
REPORTS = ROOT / '.runtime' / 'journal-ai-eval'
SPLITS = {'development', 'validation', 'test'}
BASE_FIELDS = {
    'category': 'note', 'description': '', 'precision': 'unknown', 'year': '',
    'month': '', 'day': '', 'time': '', 'timezone': 'Africa/Nairobi',
    'fold': '', 'severity': '', 'concern_id': '',
}
SYMPTOMS = ('headache', 'head hurt', 'pain', 'nausea', 'dizzy', 'cough',
            'sore throat', 'felt weak', 'felt tired', 'stomach discomfort',
            'felt unwell')
def sha(data):
    return hashlib.sha256(data).hexdigest()


def baseline(case):
    """A deliberately narrow rule baseline; unsupported text stays unknown."""
    text = case['text']
    lower = text.casefold()
    family_only = bool(re.search(r'\b(?:my aunt|my uncle|my mother|my father|my sister|my brother)\b', lower))
    hypothetical = bool(re.search(r'\bif i (?:get|have|feel)\b', lower))
    negated_only = bool(re.search(r'\bno\s+(?:headache|nausea|pain|cough)\b', lower))
    symptom = any(re.search(r'\b' + re.escape(word) + r'\b', lower) for word in SYMPTOMS)
    category = 'symptom' if symptom and not (family_only or hypothetical or negated_only) else 'note'

    occurrence = {'precision': 'unknown', 'year': None, 'month': None, 'day': None}
    dates = list(re.finditer(r'(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)', text))
    rels = list(re.finditer(r'\b(today|yesterday)\b', lower))
    uncertain = bool(re.search(r'\b(?:not sure|unsure|sometime|cannot remember which day|do not know the day)\b', lower))
    if not uncertain and len(dates) == 1 and not rels:
        y, m, d = map(int, dates[0].groups())
        try:
            date(y, m, d)
            occurrence = {'precision': 'day', 'year': y, 'month': m, 'day': d}
        except ValueError:
            pass
    elif not uncertain and not dates and len(rels) == 1:
        ref = date.fromisoformat(case['as_of'])
        found = ref if rels[0].group(1) == 'today' else date.fromordinal(ref.toordinal() - 1)
        occurrence = {'precision': 'day', 'year': found.year, 'month': found.month, 'day': found.day}

    number = r'(?:10|[0-9]|zero|one|two|three|four|five|six|seven|eight|nine|ten)'
    severity = None
    match = re.search(r'(?<!\w)' + number + r'\s*(?:/\s*10|out of 10)(?!\w)', lower)
    if match and not re.search(r'\b(?:not|never|no)\b.{0,32}' + number + r'\s*(?:/\s*10|out of 10)', lower):
        nums = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
        raw = re.match(number, match.group()).group()
        severity = int(raw) if raw.isdigit() else nums[raw]
    times = list(re.finditer(r'(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d(?!\d)', text))
    clock = times[0].group() if len(times) == 1 else None
    return {'category': category, **occurrence, 'time': clock, 'severity': severity}


def score(actual, expected):
    fields = ('category', 'precision', 'year', 'month', 'day', 'time', 'severity')
    matches = {field: actual.get(field) == expected.get(field) for field in fields}
    return {'field_matches': matches, 'exact_fields': sum(matches.values()),
            'field_count': len(fields), 'exact_match': all(matches.values())}


def failure_category(code):
    """Map safe validator codes to stable, content-free evaluation stages."""
    if code == 'generation_incomplete': return 'generation_incomplete'
    if code == 'invalid_model_json': return 'json_parsing'
    if code == 'output_schema_invalid': return 'structural_schema'
    if code == 'citation_invalid': return 'evidence_quotation'
    if code in ('category_unsupported','category_context_unsupported'): return 'category_validation'
    if code in ('date_unsupported', 'relative_date_unsupported'): return 'date_validation'
    if code == 'time_unsupported': return 'time_validation'
    if code in ('severity_unsupported', 'severity_negated'): return 'severity_validation'
    if code == 'model_response_invalid': return 'model_response_structure'
    return 'other_output_validation'


def is_invalid_evidence(result):
    """Count evidence failures only when validation actually reached evidence."""
    if result.get('failure_category') == 'evidence_quotation':
        return True
    grading = result.get('grading', {})
    return result.get('validator_accepted') is True and grading.get('evidence_valid') is False


def output_failure_diagnostics(results):
    """Print only the safe classifications already constructed by validation."""
    fields=('case_id','failure_category','failure_code','failure_diagnostic')
    return [{key:item[key] for key in fields if key in item}
            for item in results if item.get('status')=='invalid_response']


def reject_output(result, code, diagnostic=None):
    category = failure_category(code)
    result.update({'status': 'invalid_response', 'response_received': True,
        'validator_accepted': False, 'failure_category': category,
        'failure_code': code, 'latency_seconds': result.get('latency_seconds')})
    if diagnostic:
        # The pipeline assembles this allowlisted metadata without model text.
        result['failure_diagnostic'] = diagnostic
    result['grading'] = {'schema_valid': False, 'evidence_valid': None,
        'passed': False, 'exact_match': False,
        'field_matches': {field: False for field in
            ('category', 'precision', 'year', 'month', 'day', 'time', 'severity')}}


def check_manifest():
    raw = FIXTURE.read_bytes()
    data = json.loads(raw)
    if data.get('version') != 'comfort-journal-ai-v1' or data.get('license') != 'CDLA-Permissive-2.0':
        raise ValueError('Unexpected dataset version or license.')
    ids = set()
    counts = {split: 0 for split in SPLITS}
    for case in data['cases']:
        if case['id'] in ids or case['split'] not in SPLITS:
            raise ValueError('Duplicate case ID or unsupported split.')
        ids.add(case['id']); counts[case['split']] += 1
        expected = case['expected']
        if not set(expected).issuperset({'category','precision','year','month','day','time','severity'}):
            raise ValueError('Incomplete expected fields in ' + case['id'])
        for field, quote in case['evidence'].items():
            if quote is not None and quote not in case['text']:
                raise ValueError('Expected evidence is not verbatim in ' + case['id'] + ':' + field)
        if case['text'] and expected['category'] not in ('note','symptom'):
            raise ValueError('Unsupported category in ' + case['id'])
    if any(counts[split] == 0 for split in SPLITS):
        raise ValueError('All three frozen evaluation splits must be non-empty.')
    baseline_results = [score(baseline(case), case['expected']) for case in data['cases'] if case['text']]
    total = sum(r['exact_fields'] for r in baseline_results)
    fields = sum(r['field_count'] for r in baseline_results)
    return {'version': data['version'], 'sha256': sha(raw), 'case_count': len(data['cases']),
            'split_counts': counts, 'baseline_cases_scored': len(baseline_results),
            'baseline_field_accuracy': round(total / fields, 4) if fields else 0,
            'baseline_exact_case_accuracy': round(sum(r['exact_match'] for r in baseline_results) / len(baseline_results), 4) if baseline_results else 0,
            'baseline_note': 'Narrow deterministic rules; empty input is a preflight rejection, not inferred.'}


def select_cases(cases, split, limit=0, case_ids=None):
    requested_ids = set(case_ids or [])
    known_ids = {case['id'] for case in cases}
    unknown_ids = requested_ids - known_ids
    if unknown_ids:
        raise ValueError('Unknown case ID(s): ' + ', '.join(sorted(unknown_ids)))
    if requested_ids and len(requested_ids) != len(case_ids):
        raise ValueError('Duplicate case IDs are not allowed.')
    selected = [case for case in cases
                if (requested_ids and case['id'] in requested_ids)
                or (not requested_ids and (split == 'all' or case['split'] == split))]
    if limit:
        selected = selected[:limit]
    return selected


def evaluate(config, split, limit, case_ids=None):
    sys.path.insert(0, str(SOURCE))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'continuity.settings')
    import django
    django.setup()
    from records import evidence_pipeline as pipeline
    from records.journal_ai import (PROMPT_VERSION, SYSTEM as JOURNAL_SYSTEM,
        JournalOutputFailure, output_schema, validate)
    from records.journal_extraction import VERSION as NORMALIZATION_VERSION
    from intelligence.trial import available_models

    raw = FIXTURE.read_bytes()
    manifest = json.loads(raw)
    selected = select_cases(manifest['cases'], split, limit, case_ids)
    report = {'mode': 'live_synthetic_journal_evaluation', 'dataset_version': manifest['version'],
        'dataset_sha256': sha(raw), 'harness_sha256': sha(Path(__file__).read_bytes()),
        'prompt_version': PROMPT_VERSION, 'prompt_sha256': sha(JOURNAL_SYSTEM.encode()),
        'output_schema_sha256': sha(json.dumps(output_schema(),sort_keys=True,separators=(',',':')).encode()),
        'output_schema_mode': 'source_clock_candidates_v1', 'normalization_method': NORMALIZATION_VERSION,
        'accuracy_scope': 'validated_hybrid_proposals_after_source_normalization',
        'model': config['model'], 'split': split, 'selected_case_ids': [case['id'] for case in selected],
        'planned_cases': len(selected), 'results': []}
    preflight_error = None
    try:
        available_models(config)
    except TrialError as error:
        preflight_error = str(error)
        report['model_preflight_error'] = preflight_error
    for case in selected:
        result = {'case_id': case['id'], 'case_sha256': sha(case['text'].encode()),
                  'split': case['split'], 'response_received': False}
        if preflight_error:
            result.update({'status': 'not_attempted', 'safe_error': preflight_error})
            report['results'].append(result)
            continue
        started = time.perf_counter()
        if not case['text'].strip():
            result.update({'status': 'preflight_rejected_empty', 'latency_seconds': 0.0,
                           'grading': {'preflight_match': case['expected'].get('preflight') == 'rejected_empty',
                                       'schema_valid': None,
                                       'passed': case['expected'].get('preflight') == 'rejected_empty'}})
            report['results'].append(result)
            continue
        ref = datetime.fromisoformat(case['as_of']).replace(tzinfo=timezone.utc)
        request = SimpleNamespace(input_snapshot=case['text'], reference_at=ref,
                                  reference_timezone=manifest['reference_timezone'], draft_id=None)
        decoded_metadata = {}
        try:
            def validate_case(decoded):
                actual = validate(decoded, request, BASE_FIELDS)
                decoded_metadata['abstained'] = decoded['abstained']
                return actual

            def record_case(provenance):
                # Hash only: contextual schemas contain source clock values.
                result['output_schema_sha256']=provenance['configuration']['output_schema_sha256']

            actual, trace = pipeline.invoke('journal_interpretation', case['text'],
                lambda: None, validate_case, record_case,
                '\nTrusted reference date: ' + case['as_of'] +
                '\nTrusted timezone: ' + manifest['reference_timezone'])
            elapsed = round(time.perf_counter() - started, 4)
            result.update({'response_received': True, 'validator_accepted': True,
                'field_abstentions':actual['field_abstentions'],
                'discarded_model_fields':actual['discarded_model_fields'],
                'source_normalized_fields':actual['source_normalized_fields']})
            values = actual['fields']
            normalized = {'category': values['category'], 'precision': values['precision'],
                'year': int(values['year']) if values['year'] else None,
                'month': int(values['month']) if values['month'] else None,
                'day': int(values['day']) if values['day'] else None,
                'time': values['time'] or None,
                'severity': int(values['severity']) if values['severity'] != '' else None}
            field_score = score(normalized, case['expected'])
            evidence_ok = all((quote is None and field not in actual['evidence']) or
                              (quote is not None and field in actual['evidence'] and quote in actual['evidence'][field]['quote'])
                              for field, quote in case['evidence'].items())
            result.update({'latency_seconds': elapsed, 'usage': trace['usage'],
                'grading': {**field_score, 'schema_valid': True, 'evidence_valid': evidence_ok,
                            'abstained': decoded_metadata['abstained'], 'passed': field_score['exact_match'] and evidence_ok}})
            result['status'] = 'response_received'
        except TrialError as error:
            result.update({'status': 'request_failed',
                'latency_seconds': round(time.perf_counter() - started, 4), 'safe_error': str(error)})
        except pipeline.OutputFailure as error:
            result['latency_seconds'] = round(time.perf_counter() - started, 4)
            reject_output(result, error.code, error.diagnostic)
        except JournalOutputFailure as error:
            result['latency_seconds'] = round(time.perf_counter() - started, 4)
            reject_output(result, error.code, error.diagnostic)
        except (TypeError, KeyError, IndexError):
            # Defensive classification for unexpected structural/validator
            # failures after a model response, without retaining exception text.
            result['latency_seconds'] = round(time.perf_counter() - started, 4)
            reject_output(result, 'output_validation_internal', {'stage': 'output_validation_internal'})
        report['results'].append(result)
    attempted = report['results']
    timed = [item for item in attempted if isinstance(item.get('latency_seconds'), (int, float))
             and item.get('status') in ('response_received', 'invalid_response', 'request_failed')]
    latencies = [item['latency_seconds'] for item in timed]
    graded = [item['grading'] for item in attempted if 'grading' in item]
    scored = [item for item in attempted if item.get('response_received') and 'field_matches' in item.get('grading', {})]
    fields = ('category','precision','year','month','day','time','severity')
    field_matches = {field: sum(bool(item['grading']['field_matches'].get(field)) for item in scored) for field in fields}
    field_denominator = len(scored) * len(fields)
    sorted_latencies = sorted(latencies)
    percentile = lambda p: sorted_latencies[min(len(sorted_latencies)-1, int((len(sorted_latencies)-1)*p))] if sorted_latencies else None
    not_attempted = [item['case_id'] for item in attempted if item.get('status') == 'not_attempted']
    request_failures = [item['case_id'] for item in attempted if item.get('status') == 'request_failed']
    invalid_responses = [item['case_id'] for item in attempted if item.get('status') == 'invalid_response']
    invalid_output_ids = [item['case_id'] for item in attempted
        if item.get('status') == 'invalid_response'
        or item.get('grading', {}).get('schema_valid') is False
        or item.get('grading', {}).get('evidence_valid') is False]
    invalid_evidence = [item['case_id'] for item in attempted if is_invalid_evidence(item)]
    response_count = sum(bool(item.get('response_received')) for item in attempted)
    accepted_count = sum(item.get('validator_accepted') is True for item in attempted)
    inference_cases = sum(item.get('status') in ('response_received', 'invalid_response', 'request_failed')
                         for item in attempted)
    report['summary'] = {'attempted_cases': len(attempted), 'graded_cases': len(graded),
        'transport_successes': response_count,
        'successful_responses_received': response_count,
        'validator_accepted_outputs': accepted_count,
        'normalization_method': NORMALIZATION_VERSION,
        'accuracy_scope': 'validated_hybrid_proposals_after_source_normalization',
        'proposals_with_discarded_optional_suggestions': sum(bool(item.get('discarded_model_fields')) for item in attempted),
        'field_review_diagnostics': [{key:item[key] for key in ('case_id','field_abstentions','discarded_model_fields','source_normalized_fields')
                                    if key in item} for item in attempted if item.get('validator_accepted')],
        'request_failures': len(request_failures), 'request_failure_case_ids': request_failures,
        'invalid_responses': len(invalid_responses), 'invalid_response_case_ids': invalid_responses,
        'invalid_outputs': len(invalid_output_ids), 'invalid_output_case_ids': invalid_output_ids,
        'output_failure_diagnostics': output_failure_diagnostics(attempted),
        'invalid_evidence_cases': len(invalid_evidence), 'invalid_evidence_case_ids': invalid_evidence,
        'not_attempted_cases': len(not_attempted), 'not_attempted_case_ids': not_attempted,
        'preflight_empty_cases': sum(item.get('status') == 'preflight_rejected_empty' for item in attempted),
        'valid_schema_cases': sum(item.get('schema_valid') is True for item in graded),
        'passed_cases': sum(item.get('passed') is True for item in graded),
        'field_matches': field_matches,
        'field_accuracy': round(sum(field_matches.values()) / field_denominator, 4) if field_denominator else None,
        'exact_case_accuracy': round(sum(bool(item['grading'].get('exact_match') and item['grading'].get('evidence_valid'))
                                         for item in scored) / len(scored), 4) if scored else None,
        'accuracy_denominator_model_responses': len(scored),
        'request_failure_rate': round(len(request_failures) / inference_cases, 4) if inference_cases else None,
        'median_latency_seconds': statistics.median(latencies) if latencies else None,
        'p95_latency_seconds': percentile(.95),
        'complete': len(attempted) == len(selected) and not not_attempted,
        'all_requests_succeeded': len(attempted) == len(selected) and not not_attempted and not request_failures}
    REPORTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = REPORTS / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8] + '.json')
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path, report['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'run'))
    parser.add_argument('--split', choices=('development','validation','test','all'), default='development')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--case-ids', nargs='+', metavar='CASE_ID',
                        help='Run only these frozen synthetic case IDs, in manifest order.')
    args = parser.parse_args()
    try:
        summary = check_manifest()
        if args.command == 'check':
            print(json.dumps(summary, indent=2)); return 0
        if args.limit < 0:
            raise ValueError('--limit must be nonnegative.')
        path, result = evaluate(configuration(), args.split, args.limit, args.case_ids)
        print('Saved local fictional evaluation: ' + str(path))
        print(json.dumps({'dataset': summary, 'evaluation': result}, indent=2))
        return 0 if result['complete'] and result['all_requests_succeeded'] and not result['invalid_outputs'] else 1
    except (OSError, ValueError, TrialError) as error:
        print('Evaluation unavailable: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
