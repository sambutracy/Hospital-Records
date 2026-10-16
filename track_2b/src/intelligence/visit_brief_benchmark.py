"""Synthetic visit-brief evaluation using the production planner and validator.

The deterministic baseline selects the planner's area hints; it is not Apertus.
Live requests use the existing evidence pipeline and its credential-file handler.
No patient records, database queries, raw model responses or provider error bodies
are read or stored by this evaluator. Authored phrase screens measure information
retention, not clinical correctness or a clinician's judgement.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'data' / 'visit-brief-evaluation-v1.json'
REPORTS = ROOT / '.runtime' / 'visit-brief-eval'
AREAS = frozenset(('purpose', 'medications', 'history', 'symptoms', 'findings',
                   'followup', 'function', 'coordination', 'preferences', 'basics'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load_fixture(path=FIXTURE):
    raw = Path(path).read_bytes()
    suite = json.loads(raw)
    if (suite.get('version') != 'comfort-visit-brief-evaluation-v1'
            or suite.get('license') != 'CDLA-Permissive-2.0'
            or suite.get('synthetic_only') is not True):
        raise ValueError('Expected the separate fictional visit-brief corpus.')
    if len(suite.get('cases', [])) != 4:
        raise ValueError('Expected four authored fictional cases.')
    ids = set()
    for case in suite['cases']:
        if not isinstance(case.get('id'), str) or case['id'] in ids:
            raise ValueError('Duplicate or invalid case ID.')
        ids.add(case['id'])
        if not set(case['expected_areas']).issubset(AREAS):
            raise ValueError('Unknown expected section.')
        if not 1 <= len(case['sources']) <= 30:
            raise ValueError('Invalid fictional source count.')
        source_ids = [source['id'] for source in case['sources']]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError('Duplicate fictional source IDs.')
        source_text = '\n'.join(page for source in case['sources']
                                for page in source['pages']).casefold()
        facts = set()
        for target in case['fact_targets']:
            if target['id'] in facts or not target['any']:
                raise ValueError('Duplicate or empty authored fact target.')
            facts.add(target['id'])
            if not any(phrase.casefold() in source_text for phrase in target['any']):
                raise ValueError('An authored fact target is absent from its source.')
    return suite, sha(raw)


def context_for(case):
    """Construct immutable-looking fictional objects; no ORM access is needed."""
    workspace_id = uuid.uuid5(uuid.NAMESPACE_URL, 'comfort-visit-brief/' + case['id'])
    sources = []
    for index, document in enumerate(case['sources'], 1):
        source_id = 's' + str(index)
        version_id = uuid.uuid5(workspace_id, document['id'])
        document_text = '\n'.join(document['pages'])
        version = SimpleNamespace(pk=version_id, sha256=sha(document_text.encode()),
                                  original_filename=document['filename'])
        chunks = [{'id':f'{source_id}-c{page}', 'text':text,
                   'locator':{'kind':'source_text', 'page':page}}
                  for page, text in enumerate(document['pages'], 1)]
        sources.append(SimpleNamespace(source_label=source_id, source_version=version,
            source_version_id=version_id, workspace_id=workspace_id, chunks=chunks,
            fixture_id=document['id']))
    coverage = {'included_records':len(sources), 'accessible_records_at_request':len(sources),
                'snapshot':True, 'imaging_pixels_included':False,
                'text_available_sources':len(sources), 'truncated_sources':0}
    task = SimpleNamespace(kind='packet_overview', pk=uuid.uuid5(workspace_id, 'task'),
        workspace_id=workspace_id, packet_revision_id=uuid.uuid5(workspace_id, 'packet'),
        coverage=coverage, parameters={'visit_brief':True, 'packet_id':str(workspace_id),
            'visit_context':{'version':'visit-context-v1', 'as_of':case['as_of'],
                'visit':case['visit'], 'included':{'profile':False, 'medications':False,
                    'care':False, 'journal':False}, 'entries':[], 'coverage':{}}})
    context = {'task':task.kind, 'request':task.parameters, 'coverage':coverage,
        'sources':[{'source_id':source.source_label,
                    'chunks':[{'chunk_id':chunk['id'], 'text':chunk['text'],
                               'origin':chunk['locator']['kind']}
                              for chunk in source.chunks]} for source in sources]}
    return task, context, sources


def _candidate_id(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise ValueError('The visit-brief planner returned an unsupported candidate ID.')


def baseline(plan):
    """Deterministic area-hint grouping, explicitly separate from real Apertus."""
    sections = {}
    total = 0
    for candidate, entry in plan['evidence'].items():
        area = entry.get('area') or entry.get('hint') or 'history'
        if area not in AREAS:
            continue
        if total >= 28 or len(sections.get(area, [])) >= 8:
            continue
        sections.setdefault(area, []).append(_candidate_id(candidate))
        total += 1
    return {'sections':[{'area':area, 'evidence':values} for area, values in sections.items()]}


def grade(case, payload, plan):
    """Score only already accepted source selections against authored targets."""
    evidence = {_candidate_id(key):value for key, value in plan['evidence'].items()}
    selections = [ident for section in payload['sections'] for ident in section['evidence']]
    texts = [evidence[ident]['text'] for ident in selections]
    normalized = [' '.join(text.casefold().split()) for text in texts]
    duplicate_count = sum(count - 1 for count in Counter(normalized).values() if count > 1)
    text = '\n'.join(texts).casefold()
    present = {section['area'] for section in payload['sections'] if section['evidence']}
    sections = {area:area in present for area in case['expected_areas']}
    facts = {target['id']:any(phrase.casefold() in text for phrase in target['any'])
             for target in case['fact_targets']}
    forbidden = [phrase for phrase in case['forbidden_phrases'] if phrase.casefold() in text]
    provenance = {}
    for target in case.get('shared_provenance_targets', []):
        matching = [evidence[ident] for ident in selections
                    if target['contains'].casefold() in evidence[ident]['text'].casefold()]
        cited = {ref['source_label'] for item in matching for ref in item.get('refs', [])}
        provenance[target['contains']] = len(cited) >= target['minimum_sources']
    return {'section_matches':sections,
        'section_coverage':sum(sections.values()) / len(sections) if sections else None,
        'fact_matches':facts, 'field_accuracy':sum(facts.values()) / len(facts) if facts else None,
        'exact_case_match':all(sections.values()) and all(facts.values()) and all(provenance.values()) and not forbidden
            and duplicate_count <= case['maximum_duplicate_passages'],
        'shared_provenance_matches':provenance,
        'duplicate_passages':duplicate_count, 'forbidden_phrase_flags':forbidden,
        'selected_evidence_count':len(selections),
        'limitation':'Authored phrase and section screens; no clinical or independent human validation.'}


def _summary(rows, selected_count, live):
    valid = [row for row in rows if row['status'] == 'valid_output']
    attempted = [row for row in rows if row['status'] != 'unattempted']
    latencies = [row['latency_seconds'] for row in attempted if row.get('latency_seconds') is not None]
    successful_latency = [row['latency_seconds'] for row in valid if row.get('latency_seconds') is not None]
    section_denominator = sum(len(row.get('grading', {}).get('section_matches', {})) for row in rows)
    section_hits = sum(sum(row.get('grading', {}).get('section_matches', {}).values()) for row in rows)
    fact_denominator = sum(len(row.get('grading', {}).get('fact_matches', {})) for row in rows)
    fact_hits = sum(sum(row.get('grading', {}).get('fact_matches', {}).values()) for row in rows)
    attempted_sections = sum(row.get('expected_section_count', 0) for row in attempted)
    attempted_facts = sum(row.get('expected_fact_count', 0) for row in attempted)
    return {'selected_cases':selected_count, 'attempted_cases':len(attempted),
        'transport_successes':sum(row.get('response_received') is True for row in rows) if live else 0,
        'valid_outputs':len(valid), 'invalid_outputs':sum(row['status'] == 'invalid_output' for row in rows),
        'request_failures':sum(row['status'] == 'request_failure' for row in rows),
        'preflight_failures':sum(row['status'] == 'preflight_failure' for row in rows),
        'unattempted_cases':[row['case_id'] for row in rows if row['status'] == 'unattempted'],
        'section_coverage_valid_outputs':section_hits / section_denominator if section_denominator else None,
        'section_coverage_attempted':section_hits / attempted_sections if attempted_sections else None,
        'field_accuracy_valid_outputs':fact_hits / fact_denominator if fact_denominator else None,
        'field_accuracy_attempted':fact_hits / attempted_facts if attempted_facts else None,
        'exact_case_accuracy_attempted':sum(row.get('grading', {}).get('exact_case_match') is True
            for row in rows) / len(attempted) if attempted else None,
        'duplicate_passages':sum(row.get('grading', {}).get('duplicate_passages', 0) for row in rows),
        'latency_seconds':{'attempted_count':len(latencies),
            'mean_attempted':statistics.mean(latencies) if latencies else None,
            'mean_valid_outputs':statistics.mean(successful_latency) if successful_latency else None,
            'median_valid_outputs':statistics.median(successful_latency) if successful_latency else None,
            'maximum_attempted':max(latencies) if latencies else None}}


def run(live=False, case_ids=None, fixture=FIXTURE, reports=REPORTS):
    """One pass without retries; a transport failure leaves later cases unattempted."""
    from intelligence.trial import TrialError
    from records import evidence_pipeline as pipeline
    from records import visit_brief

    suite, fixture_sha256 = load_fixture(fixture)
    known = {case['id'] for case in suite['cases']}
    if case_ids and (set(case_ids) - known or len(case_ids) != len(set(case_ids))):
        raise ValueError('Choose unique case IDs from this visit-brief corpus.')
    cases = [case for case in suite['cases'] if not case_ids or case['id'] in case_ids]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = Path(reports)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{stamp}-{uuid.uuid4().hex[:8]}-{"apertus" if live else "baseline"}.json'
    report = {'version':suite['version'], 'fixture_sha256':fixture_sha256,
        'harness_sha256':sha(Path(__file__).read_bytes()), 'started_at':datetime.now(timezone.utc).isoformat(),
        'synthetic_only':True, 'mode':'live_apertus' if live else 'deterministic_area_hint_baseline',
        'model_generation_requested':live, 'total_suite_cases':len(suite['cases']),
        'not_selected_cases':[case['id'] for case in suite['cases'] if case not in cases],
        'selected_cases':len(cases), 'cases':[{'case_id':case['id'], 'status':'unattempted',
            'response_received':False, 'validator_accepted':False,
            'expected_section_count':len(case['expected_areas']),
            'expected_fact_count':len(case['fact_targets'])} for case in cases],
        'limitations':'Four authored fictional text cases. No clinical review, PDF/OCR extraction evaluation, patient database or general real-world accuracy claim.'}
    # Exclusive creation guarantees that a previous result is never overwritten.
    with path.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, indent=2) + '\n')

    def save():
        report['summary'] = _summary(report['cases'], len(cases), live)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    for index, case in enumerate(cases):
        row = report['cases'][index]
        started = time.perf_counter()
        received = False
        decoded = None
        try:
            task, context, sources = context_for(case)
            plan = visit_brief.build_plan(task, context, sources)
            row['planner_coverage'] = plan.get('coverage', {})
            row['candidate_count'] = len(plan['evidence'])
            row['available_areas'] = sorted({entry.get('area') or entry.get('hint') or 'history'
                                             for entry in plan['evidence'].values()})
            if live:
                content = visit_brief.wire_context(task, plan)

                def validate(payload):
                    nonlocal received, decoded
                    received = True
                    checked = visit_brief.validate(task, payload, plan, sources)
                    decoded = payload
                    return checked

                def provenance(value):
                    # Do not serialize endpoint/configuration, model output or credentials.
                    row['model'] = value['model']
                    row['prompt_version'] = value['prompt_version']
                    safe = value.get('configuration', {})
                    row['provenance'] = {key:safe[key] for key in
                        ('pipeline_version', 'prompt_sha256', 'output_schema_sha256', 'context_sha256', 'max_tokens', 'temperature')
                        if key in safe}

                _, trace = pipeline.invoke('visit_brief', content, lambda:None, validate, provenance)
                row['usage'] = trace.get('usage', {})
            else:
                decoded = baseline(plan)
                visit_brief.validate(task, decoded, plan, sources)
            row.update(status='valid_output', response_received=received,
                       validator_accepted=True, selection=decoded, grading=grade(case, decoded, plan))
        except pipeline.ConfigurationPending:
            row.update(status='request_failure', failure_category='configuration_unavailable')
        except TrialError:
            row.update(status='request_failure', failure_category='model_access_failed')
        except pipeline.OutputFailure as error:
            row.update(status='invalid_output', response_received=live,
                       failure_category=error.code if error.code in
                           ('generation_incomplete', 'invalid_model_json', 'model_response_invalid',
                            'brief_schema_invalid', 'brief_evidence_invalid', 'brief_attribution_invalid') else 'output_validation')
        except (ValueError, KeyError, TypeError, IndexError):
            row.update(status='invalid_output' if received or not live else 'preflight_failure',
                       response_received=received,
                       failure_category='output_validation' if received or not live else 'context_preflight')
        row['latency_seconds'] = round(time.perf_counter() - started, 4)
        save()
        if row['status'] == 'request_failure':
            # Never retry credentials, transport or service failures automatically.
            break
    save()
    return path, report
