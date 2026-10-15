"""Evidence-based public summaries and private human-review worksheets."""
import json
import re
import statistics
from collections import Counter
from .prepare import PUBLIC,RUNTIME,sha,write_json


def read(name,default=None):
    path=RUNTIME/name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else (default if default is not None else {})


def distribution(values):
    values=[v for v in values if isinstance(v,(int,float))]
    return {'n':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)} if values else {'n':0}


def normalize(value):return ' '.join(value.casefold().split())


def human_review_summary(reviews,cases):
    """Bind human decisions to exact outputs; an abstention is not an assessment."""
    by_case={c['case']:c for c in cases}
    for review in reviews:
        case=by_case.get(review['case'],{})
        texts=[item['text'] for item in (case.get('validated_answer') or {}).get('items',[])] or case.get('candidate_summary_texts',[])
        if (review.get('reviewed_output_sha256')!=sha('\n'.join(texts).encode()) or
            review.get('reviewed_context_sha256')!=case.get('configuration',{}).get('context_sha256')):
            raise ValueError('Human review does not match the evaluated output/context')
    assessed=[r for r in reviews if r['judgement'] not in ('unable_to_assess','inconclusive')]
    return {'status':'subset_assessed' if assessed else 'inconclusive' if reviews else 'pending','reviews':reviews,
      'assessed_cases':len(assessed),'inconclusive_cases':len(reviews)-len(assessed),
      'summary_cases':sum(c['kind']=='packet_overview' for c in cases),'clinician_involvement':False,
      'scope':'case-level source support and completeness only; no clinical validity or population-level claim'}


def capture_for(case):
    job=case.get('task',case.get('software_job',{}));key=job.get('id')
    return read('model-captures/'+str(key)+'.json') if key else {}


def public_case(key,case,reference,reverse,dispatch):
    job=case.get('task',case.get('software_job',{}));capture=capture_for(case)
    attempts=case.get('attempts',[])
    config=job.get('configuration',{}) or (attempts[-1].get('configuration',{}) if attempts else {})
    row={'case':key,'kind':case['kind'],'patient':case['patient'],'state':job.get('state','not_attempted'),
      'scope':reference.get('scope','functional_case'),'not_run_reason':case.get('not_run_reason'),
      'baseline_case':reference.get('baseline_case'),'representation':reference.get('representation'),
      'error_code':job.get('error_code',''),'model_attempted':(bool(config) or case.get('model_attempted',False)) and config.get('model_generation_performed',True),
      'schema_and_source_quotes_valid':case.get('schema_and_source_quotes_valid'),
      'clinical_semantic_validity':'not_established','configuration':config,
      'model':job.get('model') or (attempts[-1].get('model') if attempts else None),
      'prompt_version':job.get('prompt_version') or case.get('prompt_version'),'coverage':job.get('coverage',{}),
      'human_review_required':True}
    row['requested_scope']=row['scope']
    protocol=config.get('context_serialization','')
    row['actual_protocol']=protocol or None
    required=reference.get('execution_requirement','generative').split(';',1)[0]
    row['protocol_requirement_matches']=(protocol==required if required.startswith('local-evidence-')
        else not protocol.startswith('local-evidence-')) if config and case['kind']!='metadata' else None
    if protocol.startswith('local-evidence-v'):
        version=protocol.rsplit('-v',1)[-1]
        row['scope']='local_cpu_followup' if version=='1' else 'local_cpu_v'+version+'_followup'
    row['context_document_ids']=[reverse.get(s['source_version_id'],'unmapped') for s in job.get('sources',[])]
    if case['kind']=='metadata' and not row['prompt_version']:
        from records.metadata import PROMPT,PROMPT_VERSION
        if config.get('prompt_sha256')==sha(PROMPT.encode()):
            row['prompt_version']=PROMPT_VERSION
            row['prompt_version_source']='Matched the recorded prompt hash against the unchanged production prompt'
    measurement=next((r for r in reversed(dispatch) if r['id']==job.get('id')),attempts[-1] if attempts else {})
    row['timing']={k:measurement.get(k) for k in ('queue_wait_seconds','generation_seconds','elapsed_seconds')}
    row['timing']['application_latency_seconds']=job.get('latency_seconds')
    messages=capture.get('request',{}).get('messages',[])
    row['input_characters']=sum(len(m.get('content','')) for m in messages) if messages else None
    row['provider_usage']=capture.get('response',{}).get('usage',{}) or job.get('usage',{}) or (attempts[-1].get('usage',{}) if attempts else {})
    row['provider_timings']={k:v for k,v in (capture.get('response',{}).get('timings') or {}).items() if isinstance(v,(int,float))}
    row['timing']['provider_prefill_seconds']=row['provider_timings'].get('prompt_ms',0)/1000 if 'prompt_ms' in row['provider_timings'] else None
    row['timing']['provider_decode_seconds']=row['provider_timings'].get('predicted_ms',0)/1000 if 'predicted_ms' in row['provider_timings'] else None
    choices=capture.get('response',{}).get('choices',[])
    row['provider_finish_reason']=choices[0].get('finish_reason') if choices else None
    row['private_request_available']=bool(capture)
    row['private_provider_envelope_available']=bool(capture.get('response'))
    row['capture_status']=capture.get('status','response_received' if capture else 'not_captured')
    row['safe_provider_error']=capture.get('safe_provider_error')
    row['capture_sha256']=capture.get('capture_sha256')
    if case['kind']=='packet_overview' and choices:
        try:
            candidate=json.loads(choices[0]['message']['content'])
            items=candidate.get('items',[]) if isinstance(candidate,dict) else []
            row['candidate_summary_texts']=[item['text'] for item in items if isinstance(item,dict) and isinstance(item.get('text'),str)] if isinstance(items,list) else []
            row['candidate_summary_accepted']=job.get('state')=='completed'
        except (KeyError,TypeError,ValueError):row['candidate_summary_texts']=[]
    if case['kind']=='metadata':
        candidate=case.get('prediction')
        if candidate is None and choices:
            try:candidate=json.loads(choices[0]['message']['content'])
            except (KeyError,ValueError,TypeError):candidate=None
        expected=reference['expected'];row['expected_metadata']=expected
        row['raw_candidate_fields']={field:candidate.get(field) for field in expected} if isinstance(candidate,dict) else None
        row['raw_field_matches']={field:isinstance(candidate,dict) and candidate.get(field)==value for field,value in expected.items()}
        parts=candidate.get('document_date',{}) if isinstance(candidate,dict) else {}
        row['invented_date_components']=[part for part in ('year','month','day')
          if expected['document_date'][part] is None and isinstance(parts,dict) and parts.get(part) is not None]
    for field in ('field_correct','prediction','baseline_literal_keyword','model_retrieval','expected_relevant',
        'unpopulated_reference_sources','expected_sources_in_preselection','retrieval_stage_excluded_expected',
        'included_context_count','required_phrase_screens','forbidden_phrase_flags'):
        if field in case:row[field]=case[field]
    # Publish fixture identifiers rather than environment-specific account,
    # record/version/packet UUIDs. Full binding/configuration stays private.
    def replace(value):
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items() if k not in ('packet_id','packet_revision_id','record_id','download_url','assertion_id')}
        if isinstance(value,list):return [replace(v) for v in value]
        return reverse.get(value,value) if isinstance(value,str) else value
    row['configuration']=replace(config)
    if case['kind']=='search' and config.get('source_snapshots'):
        from .evaluate import retrieval_scores
        supplied=[reverse.get(s['source_version_id'],'unmapped') for s in config['source_snapshots']]
        row['lexical_preselection_top5']=retrieval_scores(case.get('expected_relevant',[]),supplied)
    if case.get('task'):
        row['validated_answer']=replace(job.get('result',{}))
        row['excerpt_boundary_warnings']=[index for index,item in enumerate((job.get('result') or {}).get('items',[]),1)
            if re.search(r'\b(?:is|are|was|were|has|have|with|of|to|and|or|the|a|an|being)\s*$',item['text'],re.I)]
    if messages and case['kind']!='metadata':
        context=json.loads(messages[-1]['content'])
        snapshots=config.get('source_snapshots',[])
        labels={f's{i+1}':reverse.get(item['source_version_id'],'unmapped') for i,item in enumerate(snapshots)}
        chunks={labels.get(source['source_id']):normalize(' '.join(c['text'] for c in source['chunks'])) for source in context['sources']}
        evidence=reference.get('expected_evidence',[])
        row['reference_span_screens']=[{'document':item['document'],'page':item.get('page'),
          'full_quote_visible':normalize(item['quote']) in chunks.get(item['document'],'')}
          for item in evidence if 'quote' in item]
    return row


def summarize(profile,suite,state):
    evaluation=read(f'evaluation-{profile}.json');cases_ref=json.loads((PUBLIC/'evaluation-v8.json').read_text(encoding='utf-8'))
    references={c['id']:c for c in cases_ref['cases']}
    reverse={v['version_id']:key for key,v in state['documents'].items()}
    dispatch=read('dispatch-assistant.json',{'results':[]})['results']
    eligible=set(suite['profiles'][profile]['patients'])
    cases=[public_case(key,evaluation.get('cases',{}).get(key,{
        'kind':reference['kind'],'patient':reference['patient'],'not_run_reason':'No saved attempt in this execution; no model result inferred'}),
        reference,reverse,dispatch) for key,reference in references.items() if reference['patient'] in eligible]
    recovered={row['id']:row for row in read('task-timings-recovered.json',{'rows':[]})['rows']}
    for case in cases:
        job=evaluation.get('cases',{}).get(case['case'],{}).get('task',{})
        persisted=recovered.get(job.get('id'))
        if persisted:
            case['timing'].update(persisted_queue_wait_seconds=persisted['queue_wait_seconds'],
                persisted_processing_wall_seconds=persisted['processing_wall_seconds'],
                persisted_timing_origin=persisted['evidence_origin'])
    source_patients={d['id']:d['patient'] for d in suite['documents']+suite.get('auxiliary_documents',[])}
    for case in cases:
        supplied=case['context_document_ids']
        case['context_patient_isolation_passed']=all(source_patients.get(doc)==case['patient'] for doc in supplied) if supplied else None
    metadata=[c for c in cases if c['kind']=='metadata' and c['model_attempted']]
    fields={field:{'correct':sum(bool(c.get('field_correct',{}).get(field)) for c in metadata if c.get('field_correct')),
       'attempted_denominator':len(metadata)} for field in ('document_type','document_date','facility_name')}
    for item in fields.values():item['accuracy_counting_failed_attempts']=item['correct']/len(metadata) if metadata else None
    raw_fields={field:{'correct':sum(c['raw_field_matches'][field] for c in metadata),'attempted_denominator':len(metadata)}
        for field in ('document_type','document_date','facility_name')}
    searches=[c for c in cases if c['kind']=='search'];valid_searches=[c for c in searches if c.get('model_retrieval')]
    retrieval={}
    for metric in ('recall_at_5','precision_at_5','returned_precision','reciprocal_rank'):
        values=[c['model_retrieval'][metric] for c in valid_searches if c['model_retrieval'][metric] is not None]
        retrieval[metric]={'mean':statistics.mean(values) if values else None,'successful_case_denominator':len(values)}
    absent=[c for c in valid_searches if c['model_retrieval']['correct_abstention'] is not None]
    retrieval['correct_absent_abstentions']={'correct':sum(c['model_retrieval']['correct_abstention'] for c in absent),'successful_absent_cases':len(absent)}
    retrieval['attempted_searches']=sum(c['model_attempted'] for c in searches)
    retrieval['failed_or_missing_search_responses']=sum(c['state']!='completed' for c in searches)
    retrieval['failed_search_requests']=sum(c['state']=='failed' for c in searches)
    retrieval['not_run_search_cases']=sum(not c['model_attempted'] for c in searches)
    positive=[c for c in searches if c['model_attempted'] and c.get('expected_relevant')]
    retrieval['end_to_end_recall_at_5']={'mean':statistics.mean((c.get('model_retrieval') or {}).get('recall_at_5') or 0 for c in positive) if positive else None,
      'attempted_positive_case_denominator':len(positive),'scope':'whole pipeline; failed requests count as zero, not as model ranking errors'}
    metrics={'metadata':{'attempts':len(metadata),'accepted_output_field_accuracy':fields,'raw_candidate_field_accuracy':raw_fields},'retrieval':retrieval,
      'attempted_states':dict(Counter(c['state'] for c in cases if c['model_attempted'])),
      'schema_quote_valid':{'valid':sum(c['schema_and_source_quotes_valid'] is True and c['model_attempted'] for c in cases),
          'attempted':sum(c['model_attempted'] for c in cases)},
      'generation_seconds':distribution(c['timing']['generation_seconds'] for c in cases),
      'completion_tokens':distribution(c['provider_usage'].get('completion_tokens') for c in cases),
      'provider_prefill_seconds':distribution(c['timing']['provider_prefill_seconds'] for c in cases),
      'provider_decode_seconds':distribution(c['timing']['provider_decode_seconds'] for c in cases),
      'per_kind_generation_seconds':{kind:distribution(c['timing']['generation_seconds'] for c in cases if c['kind']==kind)
          for kind in ('metadata','search','packet_overview')},
      'processing_wall_seconds':distribution(c['timing'].get('persisted_processing_wall_seconds') for c in cases),
      'human_factual_preservation':'not_established','unsupported_claim_rate':'requires_independent_human_review',
      'cold_start_comparison':'not_measured; shared already-loaded model'}
    metrics['by_scope']={scope:{'planned_cases':sum(c['scope']==scope for c in cases),
       'attempted':sum(c['scope']==scope and c['model_attempted'] for c in cases),
       'valid_outputs':sum(c['scope']==scope and c['schema_and_source_quotes_valid'] is True for c in cases),
       'failed':sum(c['scope']==scope and c['state']=='failed' for c in cases)} for scope in ('functional_case','compact_control','local_cpu_followup','local_cpu_v2_followup','local_cpu_v3_followup','local_cpu_v4_followup')}
    for scope,summary in metrics['by_scope'].items():
        scoped=[c for c in searches if c['scope']==scope and c.get('model_retrieval')]
        recall=[c['model_retrieval']['recall_at_5'] for c in scoped if c['model_retrieval']['recall_at_5'] is not None]
        absent=[c for c in scoped if c['model_retrieval']['correct_abstention'] is not None]
        summary['retrieval']={'successful_positive_case_denominator':len(recall),'conditional_recall_at_5':statistics.mean(recall) if recall else None,
            'successful_absent_cases':len(absent),'correct_absent_abstentions':sum(c['model_retrieval']['correct_abstention'] for c in absent)}
    from .run import selected
    patients,actors,docs=selected(suite,profile)
    verify=read(f'verify-{profile}.json');workflow=read(f'workflows-{profile}.json')
    extract=read('processing-extract.json',{'results':[]})['results']
    resource=RUNTIME/'docker-stats-during-metadata.jsonl'
    resources=[json.loads(line) for line in resource.read_text(encoding='utf-8-sig').splitlines() if line.startswith('{')] if resource.exists() else []
    resources=[{k:row[k] for k in ('Name','CPUPerc','MemUsage','PIDs')} for row in resources if 'inference' in row.get('Name','') or 'ecosystem-worker' in row.get('Name','')]
    sampled=RUNTIME/'resource-samples.jsonl'
    series=[json.loads(line) for line in sampled.read_text(encoding='utf-8').splitlines() if line.startswith('{')] if sampled.exists() else []
    active=[row for point in series for row in point['containers'] if 'inference' in row['Name']]
    cpu=distribution(float(row['CPUPerc'].rstrip('%')) for row in active)
    result={'version':'comfort-integrated-results-v1','profile':profile,'population_sha256':sha((PUBLIC/'population.json').read_bytes()),
      'evaluation_sha256':sha((PUBLIC/'evaluation-v8.json').read_bytes()),'dataset_attribution':'DATA_CARD.md',
      'population':{'patients':len(patients),'additional_actors':len(actors),'bound_accounts':len(state['accounts']),
        'initial_documents':len(docs),'seeded_initial_documents':sum(d['id'] in state['documents'] for d in docs),
        'per_patient':{p['id']:sum(d['patient']==p['id'] and d['id'] in state['documents'] for d in docs) for p in patients},
        'auxiliary_uploads':sorted(k for k in state['documents'] if k.endswith('-AUX'))},
      'integrity':{'passed':verify.get('passed',False),'checks':len(verify.get('checks',[]))},
      'workflows':{'passed':workflow.get('passed',False),'complete':workflow.get('complete',False),'checks':workflow.get('checks',[])},
      'record_journeys':read(f'journeys-{profile}.json'),
      'extraction':{'receipts':len(extract),'states':dict(Counter(r['state'] for r in extract)),
        'bounded_batch_worker_seconds':distribution(r.get('elapsed_seconds') for r in extract)},
      'metrics':metrics,'cases':cases,'resource_samples':resources,
      'resource_series':{'samples':len(series),'inference_cpu_percent':cpu,'observations':series},
      'resource_scope':'point samples during shared CPU inference, not peaks or throughput; no isolated cold start',
      'runtime_gate':read('runtime-gate.json'),
      'regression':read('regression.json'),'clinical_validation':False,'human_semantic_review':'pending',
      'human_usability':'not_performed','stress':'mapped; not seeded or run',
      'unsupported':['trusted delegation','verified professional roles','journal events','OCR','voice assistance']}
    reviews=read(f'human-decisions-{profile}.json',{'reviews':[]})['reviews']
    result['human_semantic_review']=human_review_summary(reviews,cases)
    deployed=read('ordinary-after-cpu-update.json')
    result['deployment_verification']={key:deployed.get(key) for key in (
        'protocol','mode','existing_counts_preserved','health_http_status')}
    result['current_protocol_request_equivalence']=read('current-protocol-equivalence.json',{'rows':[]})
    return result


def build(profile,suite,state):
    result=summarize(profile,suite,state)
    write_json(PUBLIC/f'results-{profile}.json',result)
    references=json.loads((PUBLIC/'evaluation-v8.json').read_text(encoding='utf-8'))
    worksheet={'status':'pending; this is a worksheet, not completed human review','clinician_involved':False,
      'instructions':'Compare each factual statement to its exact source context. Mark supported, unsupported, contradicted or unverifiable. Separately assess dates, negation, uncertainty, medication-use attribution and omissions. Do not infer medical correctness from a literal quotation.',
      'cases':[{'case':c['case'],'expected':next(r for r in references['cases'] if r['id']==c['case']),
        'answer':c.get('validated_answer') or c.get('candidate_summary_texts') or c.get('prediction'),
        'accepted_by_application':c['state'] in ('completed','review_ready'),'reviewer':None,'entailment_decisions':[],
        'factual_preservation':None,'unsupported_claims':None,'comments':None} for c in result['cases']]}
    target=RUNTIME/f'human-review-{profile}.json'
    # Never erase a human's annotations on report regeneration.
    if target.exists():
        saved=json.loads(target.read_text(encoding='utf-8'))
        known={case['case'] for case in saved.get('cases',[])}
        saved.setdefault('cases',[]).extend(case for case in worksheet['cases'] if case['case'] not in known)
        saved['decisions_file']=f'human-decisions-{profile}.json'
        write_json(target,saved)
    else:write_json(target,worksheet)
    failed=[c for c in result['cases'] if c['model_attempted'] and c['state'] not in ('completed','review_ready')]
    excluded=[c for c in result['cases'] if c.get('retrieval_stage_excluded_expected')]
    truncated=[c for c in result['cases'] if any(not s['full_quote_visible'] for s in c.get('reference_span_screens',[]))]
    phrases=[c for c in result['cases'] if c.get('forbidden_phrase_flags') or (c.get('required_phrase_screens') and not all(c['required_phrase_screens']))]
    boundaries=[c for c in result['cases'] if c.get('excerpt_boundary_warnings')]
    population=result['population'];metrics=result['metrics']
    regression=result['regression']
    checks_verified=(regression.get('postgresql_exit_code')==0 and all(regression.get(key) for key in (
        'backend_tests_passed','frontend_tests_passed','fixture_contract_tests_passed')))
    regression_text=(f"Verification: {regression.get('backend_tests_passed')} PostgreSQL backend tests, {regression.get('frontend_tests_passed')} frontend tests and {regression.get('fixture_contract_tests_passed')} fixture contract tests passed."
        if checks_verified else 'Verification: no complete passing regression receipt is available.')
    equivalent=result['current_protocol_request_equivalence']['rows']
    equivalent_verified=bool(equivalent) and all(row['wire_equivalent'] and row['current_protocol']==result['deployment_verification']['protocol'] for row in equivalent)
    reviewed=result['human_semantic_review']['assessed_cases']
    inconclusive=result['human_semantic_review']['inconclusive_cases']
    lines=[f'# Comfort synthetic ecosystem — {profile} results','',
      '## Repository changes and compatibility','',
      'Added a separate resumable population, pinned-source manifests, guarded bounded worker/capture commands, integration evaluation, regression tests and developer instructions. Local CPU assistant generation now supports bounded extractive selection, reusing the normal immutable source snapshots, authority checks and citation validation. Authentication, database constraints, existing app data and frozen evaluation v1/v2 remain intact. The abandoned branch was removed after explicit user approval with SHA-guarded remote deletion.',
      '',regression_text+f" Frontend production build: {regression.get('frontend_production_build','not measured')}. Root make run: {regression.get('root_make_run','not measured')}; root make test: {regression.get('root_make_test','not measured')}. An existing-stack launch is not a fresh-checkout claim.",
      '',f"Ordinary app update: mode={result['deployment_verification']['mode']}, protocol={result['deployment_verification']['protocol']}, existing record/version/workspace counts preserved={result['deployment_verification']['existing_counts_preserved']}, health HTTP={result['deployment_verification']['health_http_status']}. Current-protocol source-request equivalence verified={equivalent_verified}; see the paired receipts for cases and hashes. These are not additional model samples.",
      '','## Synthetic population','',
      f"{population['patients']} patient scenarios, {population['additional_actors']} additional actors; {population['bound_accounts']} bound canonical accounts. {population['seeded_initial_documents']}/{population['initial_documents']} initial documents seeded. Every actor also has their own patient workspace.",
      '','| Patient | Initial documents |','|---|---:|']
    lines += [f'| {p} | {n} |' for p,n in population['per_patient'].items()]
    lines += ['',f"Auxiliary uploads: {', '.join(population['auxiliary_uploads']) or 'none'}. Accepted contributions are additional records, with their own original and submitter attribution.",
      '', 'Sources: pinned NHS synthetic silver notes (MIT), original morzel.net/Synthea benchmark PDFs (CC BY 4.0), and explicitly authored fixtures (CDLA-Permissive-2.0). See [data card and attribution](DATA_CARD.md), [scenario matrix](SCENARIOS.md), population/source/text locks. Source patients are never mixed across workspaces.',
      '','## Workflow and security results','',
      f"Original integrity/pagination: {result['integrity']['checks']} checks, passed={result['integrity']['passed']}. Functional authorization/journey checks: {len(result['workflows']['checks'])}, all passed={result['workflows']['passed']}, complete={result['workflows']['complete']}.",
      f"Additional record/filter/provider journeys: {len(result['record_journeys'].get('checks',[]))} checks, all passed={result['record_journeys'].get('passed',False)}.",
      'Checks cover fresh authentication/onboarding, exact packet scope, cross-recipient/source denials, actual expiry/revocation, independently granted contribution, pending/accepted/rejected boundaries, original integrity/submitter attribution, reported-role negative permissions and dual own/received contexts. Relationship labels establish no delegation or professional verification.',
      '','## Actual Apertus results','',
      'Runtime: community text-only Q4_K_M conversion of Apertus v1.5 8B (`Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF`), served locally by the pinned llama.cpp container. This is not the unchanged multimodal checkpoint. Exact weight/revision hashes, prompts, configurations and source snapshots are recorded per attempt.',
      f"Schema and source-quote validity: {metrics['schema_quote_valid']['valid']}/{metrics['schema_quote_valid']['attempted']} attempted cases. This is not a measure of semantic or clinical correctness.",
      '',f"Run scopes: `{json.dumps(metrics['by_scope'])}`. Compact single-source controls and CPU extractive follow-ups are separate from the initial functional cases. Extractive outputs are selected verbatim passages, not newly written summaries. Earlier failures remain in their original rows. Unexecuted larger cases remain labelled with their runtime-gate reason; they are not successful evaluations.",
      '','| Case | Scope | Kind | State / error | Structural/source quotes |','|---|---|---|---|---|']
    lines += [f"| {c['case']} | {c['scope']} | {c['kind']} | {c['state']} {c['error_code']} | {c['schema_and_source_quotes_valid']} |" for c in result['cases']]
    by_id={case['case']:case for case in result['cases']}
    def outcome(key):
        case=by_id.get(key)
        if not case:return 'not run'
        seconds=case['timing']['application_latency_seconds']
        return case['state']+(f' ({seconds:.1f}s)' if seconds is not None else '')+(
            ' [protocol differs: '+str(case['actual_protocol'])+']' if case['protocol_requirement_matches'] is False else '')
    lines += ['','### Local CPU comparisons','',
        '| Reference case | Original protocol | Extractive v1 | Extractive v2 | Extractive v3 | Extractive v4 |',
        '|---|---|---|---|---|---|']
    for key in ('q01','o01','q08','co01','co02','q06','o02'):
        lines.append(f'| {key} | {outcome(key)} | {outcome("cpu-"+key)} | {outcome("cpu2-"+key)} | {outcome("cpu3-"+key)} | {outcome("cpu4-"+key)} |')
    lines += ['',
        'These are separate saved attempts, not replacements. CPU v1 reduced output to evidence IDs but omitted the medication qualification in o01 and selected a bare heading in co01. CPU v2 added per-source selections and tighter search bounds but still selected administrative text. Its co01 result collection was interrupted by an SSO refresh branch; the finished task was subsequently recovered through the normal API with zero model replays. The client now uses a fresh local cookie jar and verifies the same identity on reauthentication. CPU v3 added a lexical clinical-passage prior, dated evidence and a narrative fallback. CPU v4 retains mixed clinical/administrative narrative that the earlier prior suppressed. These priors can omit important content and do not establish clinical relevance or complete coverage. These are reused development references, not an unseen test set. Timings share the development machine and are not isolated hardware benchmarks.']
    lines += ['',f"Metadata exact field accuracy, counting failed attempts: `{json.dumps(metrics['metadata'])}`.",
      '',f"Retrieval metrics on successful responses only: `{json.dumps(metrics['retrieval'])}`.",
      'Precision@5 keeps denominator five; this app returns at most three model matches. Returned precision is separate. Failed requests never count as correct absent-answer abstention. Keyword baseline, lexical preselection and full reference-span visibility are recorded separately per case.',
      '',f"Generation time seconds: `{json.dumps(metrics['per_kind_generation_seconds'])}`. Completion tokens: `{json.dumps(metrics['completion_tokens'])}`. Input size, token usage, prompt/configuration hashes, timing and valid answers are in the paired JSON. First two metadata envelopes were not captured; their validated artifacts/configuration remain available.",
      '',f"Persisted processing wall time (including failure handling, distinct from successful-response latency): `{json.dumps(metrics['processing_wall_seconds'])}`. Null failed-task generation latencies remain null; read-only task timestamps are labelled separately.",
      '','## Resources and limitations','',
      f"Extraction states across bounded receipts: `{json.dumps(result['extraction']['states'])}`. The image-only benchmark should remain needs_ocr. Extracted text is not pixel interpretation.",
      '',f"Resource observations: `{json.dumps(result['resource_samples'])}`. {result['resource_scope']}. Resource figures are point samples and cannot establish capacity, peaks or causal latency differences.",
      '', 'The 50-patient stress mapping was prepared. Original functional requests repeatedly reached the timeout; bounded CPU follow-ups now complete, but full functional quality/capacity stability has not been established, so stress remains unexecuted. Synthetic notes include encoding artifacts and repeated representations. P10 metadata defaults are conservative fixture review values, not a comprehensive annotated metadata gold standard. This small evaluation is not representative of all clinical language, dialects or conditions.',
      '','## Evidence-based engineering priorities','',
      f"1. Apertus/output handling: review failed/incomplete attempts {', '.join(c['case'] for c in failed) or '(none recorded)'}. Preserve their responses/configuration; do not hide failed runs in accuracy denominators.",
      '   Observed failures include a December month invented from a year-only 2025 document date, and a blocked overview candidate describing a document date as a patient-confirmed visit date. The overview also used escaped text that failed quotation validation. Preserve date roles and exact source quotes before presenting these outputs. These are deterministic source comparisons, not completed human or clinical judgments. Raw field matches and usable-output accuracy are reported separately.',
      f"2. Retrieval architecture: preselection omitted expected documents in {', '.join(c['case'] for c in excluded) or '(none recorded)'}. Full reference spans were absent from supplied context in {', '.join(c['case'] for c in truncated) or '(none recorded)'}. Address source ranking and passage selection separately from generation.",
      f"3. Clinical information handling: inspect phrase-screen concerns in {', '.join(c['case'] for c in phrases) or '(none recorded)'}. Screens are not entailment judgments. Complete independent statement-level human review before asserting factual-preservation or unsupported-claim rates.",
      f"   Passage-boundary warnings: {', '.join(c['case'] for c in boundaries) or '(none recorded)'}. In cpu3-o02 a selected quote ended 'current strength is', before the next source line 'unconfirmed'. Exact quotation alone does not preserve the whole qualification. Preserve contiguous wrapped statements and evaluate omissions before using an excerpt draft as a clinical handoff. The boundary heuristic is a screening aid, not human review.",
      '4. Backend integration/authorization: retain explicit permissions and negative tests. Fixture execution exposed receipt-write concurrency and Keycloak loopback protocol behavior; operation locking and exact-subject provisioning now cover these. Supported guardian/caregiver labels remain distinct from an unimplemented trusted acting context.',
      '5. Frontend/accessibility and missing capabilities: there is no new browser usability evidence in this protocol run. The audit found no voice operation, trusted delegation, professional verification, journal service or OCR. Develop and test these as explicit product capabilities; do not represent the authored scenarios as existing features.',
      '6. Resource utilization: collect isolated warmed and cold runs at multiple controlled input sizes before choosing hardware or making throughput claims. Current inference shares the development machine.',
      '','## Scope of conclusions','',
      f'Human semantic review: {reviewed} summary cases assessed; {inconclusive} review responses were inconclusive. Remaining cases stay unreviewed, and an unable-to-assess response is not a correctness label. Actual usability testing and clinician validation were not performed. The worksheet is private and preserves annotations. These are measured software/model-development results using synthetic information, not evidence of clinically validated outcomes or production readiness.']
    path=PUBLIC/f'RESULTS-{profile}.md';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'report':str(path),'machine_readable':str(PUBLIC/f'results-{profile}.json'),'human_review':str(target)}
