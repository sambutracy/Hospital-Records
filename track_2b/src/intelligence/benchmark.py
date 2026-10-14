"""Frozen synthetic text evaluation using the production prompts/schema/validator.

No patient database is read or written. Deterministic lexical screens are not clinical review.
"""
import hashlib
import json
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
from datetime import datetime, timezone
from .trial import available_models, configuration, redact, request_json, TrialError, LOCAL_TEXT_MODEL

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'data' / 'comfort-evaluation-v2.json'


def load_fixture(path=FIXTURE):
    raw = path.read_bytes()
    suite = json.loads(raw)
    documents = {doc['id']: doc for doc in suite['documents']}
    if len(documents) != len(suite['documents']) or len(documents) != 30:
        raise ValueError('Expected 30 unique authored sources.')
    cases = suite['queries'] + suite['overviews']
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Duplicate evaluation case IDs.')
    for case in cases:
        if any(key not in documents for key in case.get('sources', case.get('relevant', []))):
            raise ValueError('Unknown evaluation source.')
    return suite, documents, hashlib.sha256(raw).hexdigest()


def keyword_results(query, documents):
    # Mirrors the app's case-insensitive literal filename/type/facility/text baseline.
    return [key for key, doc in documents.items() if query.casefold() in
            (' '.join([doc['filename'], doc['document_type'], doc['facility'], doc['text']])).casefold()]


def retrieval_scores(expected, actual):
    expected = set(expected)
    actual = actual[:5]
    hits = len(expected.intersection(actual))
    return {'recall_at_5': hits / len(expected) if expected else None,
            'precision_at_5': hits / len(actual) if actual else None,
            'reciprocal_rank': next((1 / (index + 1) for index, key in enumerate(actual) if key in expected), 0.0) if expected else None,
            'correct_abstention': not actual if not expected else None}


def context_for(case, documents):
    import uuid
    selected = list(documents) if case['kind'] == 'search' else case['sources']
    sources = []
    workspace = uuid.UUID('00000000-0000-4000-8000-000000000001')
    for index, key in enumerate(selected):
        doc = documents[key]
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, 'comfort-synthetic-v1/' + key)
        label = f's{index + 1}'
        chunks = [{'id':label + '-c0', 'text':doc['text'], 'locator':{'kind':'source_text','page':1}}]
        version = SimpleNamespace(pk=version_id, sha256=hashlib.sha256(doc['text'].encode()).hexdigest(),
                                  original_filename=doc['filename'])
        sources.append(SimpleNamespace(source_label=label, source_version=version,
                       source_version_id=version_id, workspace_id=workspace, chunks=chunks, fixture_id=key))
    parameters = {'query':case['query']} if case['kind'] == 'search' else {'packet_id':str(workspace)}
    task = SimpleNamespace(kind=case['kind'], parameters=parameters, packet_revision_id=workspace)
    context = {'task':case['kind'], 'request':parameters,
        'coverage':{'included_records':len(sources),'accessible_records_at_request':len(sources),
                    'snapshot':True,'imaging_pixels_included':False,'text_available_sources':len(sources),
                    'truncated_sources':0},
        'sources':[{'source_id':source.source_label,'chunks':[{'chunk_id':chunk['id'],
                    'text':chunk['text'],'origin':'source_text'} for chunk in source.chunks]} for source in sources]}
    return task, context, sources


def grade(case, payload, sources, task):
    from records.assistant import validate_response
    result = {'format_and_quotes_valid':False}
    try:
        checked = validate_response(task, payload, sources)
    except (ValueError, KeyError, TypeError, IndexError):
        return result
    result['format_and_quotes_valid'] = True
    if case['kind'] == 'search':
        labels = {source.source_label:source.fixture_id for source in sources}
        selected = [labels[match['source_id']] for match in payload['matches']]
        result.update(retrieval_scores(case['relevant'], selected))
        result['selected_sources'] = selected
    else:
        text = '\n'.join(item['text'] for item in checked['items']).casefold()
        # Authored reference phrases screen information preservation only.
        result['required_phrase_groups_present'] = [any(phrase.casefold() in text for phrase in group)
                                                    for group in case['required_any']]
        result['forbidden_phrases_present'] = [phrase for phrase in case['forbidden'] if phrase.casefold() in text]
        result['information_screen_passed'] = (all(result['required_phrase_groups_present'])
                                            and not result['forbidden_phrases_present'])
        result['limitations'] = 'Lexical screen; citation validity does not prove that paraphrases are entailed. Human semantic/clinical review remains required.'
    return result


def run(live=False, case_ids=None, output=None, request_timeout=600):
    suite, documents, fixture_hash = load_fixture()
    cases = suite['queries'] + suite['overviews']
    if case_ids:
        unknown = set(case_ids) - {case['id'] for case in cases}
        if unknown:
            raise ValueError('Unknown case selection.')
        cases = [case for case in cases if case['id'] in case_ids]
    report = {'suite_version':suite['version'], 'fixture_sha256':fixture_hash,
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'started_at':datetime.now(timezone.utc).isoformat(),
        'mode':'live_apertus_synthetic_text' if live else 'offline_keyword_baseline',
        'total_suite_cases':len(suite['queries']) + len(suite['overviews']),
        'selected_cases':len(cases), 'synthetic_only':True, 'results':[],
        'baseline':[{'case_id':case['id'], 'selected_sources':keyword_results(case['query'], documents),
                    **retrieval_scores(case['relevant'], keyword_results(case['query'], documents))}
                    for case in suite['queries']],
        'limitations':'30 authored short text sources, 20 retrieval queries and 10 overview cases. No PDF/OCR, images, patient database, real-world prevalence, clinical review or production relevance preselection benchmark.'}
    path = Path(output) if output else ROOT / '.runtime' / 'evaluation' / ('live.json' if live else 'baseline.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    save()
    if live:
        from records.assistant_worker import PROMPTS, TOKEN_LIMITS
        from records.assistant import serialize_context, CONTEXT_SERIALIZATION
        from records.assistant_format import output_format
        config = configuration()
        if config['model']==LOCAL_TEXT_MODEL and config['request_timeout']==300:
            config={**config,'request_timeout':request_timeout}
        report['request_timeout_seconds']=config['request_timeout']
        try:
            available_models(config)
        except TrialError as error:
            report['preflight_error']=str(error)
            save()
            raise
        report['model_identity'] = config['identity']
        report['model_name'] = config['model']
        report['parameters'] = {'temperature':0, 'max_tokens_by_task':TOKEN_LIMITS, 'stream':False}
        report['context_serialization']=CONTEXT_SERIALIZATION
        report['cache_prompt_enabled']=config['model']==LOCAL_TEXT_MODEL
        for case in cases:
            task, context, sources = context_for(case, documents)
            version, prompt = PROMPTS[case['kind']]
            constrained = {**output_format(task, sources),'cache_prompt':True} if config['model']==LOCAL_TEXT_MODEL else {}
            request = {'model':config['model'], 'temperature':0,'stream':False,'max_tokens':TOKEN_LIMITS[case['kind']], **constrained,
                'messages':[{'role':'system','content':prompt},
                            {'role':'user','content':serialize_context(context)}]}
            row = {'case_id':case['id'],'kind':case['kind'],'prompt_version':version,
                'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                'context_sha256':hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()}
            started = time.perf_counter()
            report['in_flight_case_id']=case['id']
            save()
            transport_failure = False
            try:
                response = request_json(config, 'chat/completions', request)
                row['response'] = redact(response, config['key'])
                choice = response['choices'][0]
                if choice.get('finish_reason') != 'stop':
                    raise ValueError('Incomplete generation.')
                payload = json.loads(choice['message']['content'])
                if config['key'] and config['key'] in json.dumps(payload):
                    raise ValueError('Provider echoed credentials.')
                row['grading'] = grade(case, payload, sources, task)
            except TrialError as error:
                row['error'] = str(error)
                transport_failure = True
            except (ValueError, KeyError, IndexError, TypeError):
                row['grading'] = {'format_and_quotes_valid':False}
            row['latency_seconds'] = round(time.perf_counter() - started, 3)
            report['results'].append(row)
            report.pop('in_flight_case_id',None)
            save()
            print(f"{case['id']}: {'valid' if row.get('grading',{}).get('format_and_quotes_valid') else 'failed'}; {row['latency_seconds']} s", flush=True)
            if transport_failure:
                break  # Preserve partial result; no automated retries or further charged requests.
    scored = [row for row in report['results'] if row.get('grading',{}).get('format_and_quotes_valid')]
    searches = [row['grading'] for row in scored if row['kind'] == 'search']
    positive_ids={case['id'] for case in suite['queries'] if case['relevant']}
    attempted_positive=[row for row in report['results'] if row['case_id'] in positive_ids]
    attempted_negative=[row for row in report['results'] if row['kind']=='search' and row['case_id'] not in positive_ids]
    valid_recalls=[row['recall_at_5'] for row in searches if row['recall_at_5'] is not None]
    report['summary'] = {'attempted_cases':len(report['results']), 'format_and_quotes_valid':len(scored),
        'all_selected_cases_attempted':len(report['results']) == len(cases) if live else False,
        'baseline_mean_recall_at_5':statistics.mean(row['recall_at_5'] for row in report['baseline'] if row['recall_at_5'] is not None),
        'baseline_positive_queries':len(positive_ids),
        'baseline_correct_abstentions':sum(row['correct_abstention'] is True for row in report['baseline']),
        'baseline_abstention_queries':len(suite['queries'])-len(positive_ids),
        'model_mean_recall_at_5_valid_responses':statistics.mean(valid_recalls) if valid_recalls else None,
        'model_mean_recall_at_5_attempted_positive_queries':sum(row.get('grading',{}).get('recall_at_5') or 0 for row in attempted_positive)/len(attempted_positive) if attempted_positive else None,
        'model_correct_abstentions':sum(row.get('grading',{}).get('correct_abstention') is True for row in attempted_negative),
        'model_attempted_abstention_queries':len(attempted_negative),
        'overview_information_screen_passed':sum(row['grading'].get('information_screen_passed',False) for row in scored),
        'mean_latency_seconds':statistics.mean(row['latency_seconds'] for row in report['results']) if report['results'] else None}
    save()
    print(json.dumps(report['summary']), flush=True)
    return report
