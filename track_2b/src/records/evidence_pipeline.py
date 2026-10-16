"""Bounded inference primitives; domain services own authority and persistence.

No scheduler, credentials, retries, domain records or publication authority live
here. Each client supplies live checkpoints and its own strict output validator.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Callable


VERSION = 'comfort-evidence-pipeline-v1'


class ConfigurationPending(Exception):
    pass


@dataclass(frozen=True)
class Evidence:
    label: str
    text: str
    metadata_json: str = '{}'

    @property
    def sha256(self):
        serialized=json.dumps({'text':self.text,'metadata':json.loads(self.metadata_json)},sort_keys=True,separators=(',',':'),ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass(frozen=True)
class TaskSpec:
    kind: str
    prompt_version: str
    system: str
    schema: Callable
    max_tokens: int
    max_evidence: int
    max_characters: int


_specs = {}


def register(spec):
    if spec.kind in _specs and _specs[spec.kind] != spec:
        raise ValueError('A task contract is already registered.')
    _specs[spec.kind] = spec
    return spec


def specification(kind):
    if kind not in _specs:
        raise ValueError('No registered evidence task contract.')
    return _specs[kind]


def bounded(kind, evidence, checkpoint):
    """Freeze explicitly selected evidence, rejecting silent scope expansion."""
    checkpoint()
    spec=specification(kind)
    selected=tuple(evidence)
    if not 1<=len(selected)<=spec.max_evidence:
        raise ValueError('Evidence selection exceeds the task bound.')
    if any(not isinstance(item,Evidence) or not isinstance(item.label,str) or not item.label or
           not isinstance(item.text,str) or not item.text.strip() or not isinstance(item.metadata_json,str) for item in selected):
        raise ValueError('Readable, explicitly selected evidence is required.')
    if len({item.label for item in selected})!=len(selected):
        raise ValueError('Evidence labels must be unique.')
    if sum(len(item.text)+len(item.metadata_json) for item in selected)>spec.max_characters:
        raise ValueError('Evidence context exceeds the task bound.')
    return selected


def citations(values,evidence,preserve_scope=False):
    """Resolve only exact quotations to caller-supplied immutable source IDs."""
    if not isinstance(values,list) or not 1<=len(values)<=4:
        raise ValueError('One to four citations are required.')
    by_id={item.label:item for item in evidence}
    checked=[]
    for value in values:
        if not isinstance(value,dict) or set(value)!={'evidence_id','quote'}:
            raise ValueError('Unexpected citation fields.')
        item=by_id.get(value['evidence_id'])
        quote=value['quote']
        if item is None or not isinstance(quote,str) or not quote.strip() or len(quote)>500 or quote not in item.text:
            raise ValueError('Citation is outside the selected evidence.')
        start=item.text.index(quote)
        if preserve_scope:
            # A substring can omit "no", a family subject, or a conditional.
            # Display its complete source sentence, never a generated paraphrase.
            boundaries=[0]+[match.end() for match in re.finditer(r'[.!?](?=\s|$)|\n',item.text)]+[len(item.text)]
            left=max(boundary for boundary in boundaries if boundary<=start)
            right=min(boundary for boundary in boundaries if boundary>=start+len(quote))
            quote=item.text[left:right].strip()
            if len(quote)>500: raise ValueError('The cited scope is too long to preserve safely.')
            start=item.text.index(quote,left)
        checked.append({'evidence_id':item.label,'quote':quote,'start':start,'end':start+len(quote),'snapshot_sha256':item.sha256})
    return checked


def invoke(kind,content,checkpoint,validate,record,reference=''):
    """One authenticated Apertus request. Checkpoints must recheck a live lease.

    The record callback receives safe provenance only, never configuration keys.
    Patient content and provider response/error bodies are never logged here.
    """
    from intelligence.trial import TrialError, configuration, available_models, request_json
    spec=specification(kind)
    if not isinstance(content,str) or not content.strip() or len(content)>spec.max_characters:
        raise ValueError('Inference context exceeds the registered bound.')
    checkpoint()
    try:
        config=configuration()
    except TrialError:
        raise ConfigurationPending from None
    prompt=spec.system+reference
    setup=time.perf_counter()
    available_models(config)
    model_setup_seconds=time.perf_counter()-setup
    checkpoint()
    provenance={'model':config['model'],'prompt_version':spec.prompt_version,
        'configuration':{'base_url':config['base'],'request_timeout_seconds':config.get('request_timeout',90),
            'temperature':0,'max_tokens':spec.max_tokens,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'pipeline_version':VERSION,'context_sha256':hashlib.sha256(content.encode()).hexdigest()}}
    record(provenance)
    checkpoint()
    start=time.perf_counter()
    response=request_json(config,'chat/completions',{'model':config['model'],'temperature':0,'max_tokens':spec.max_tokens,'stream':False,
        'response_format':{'type':'json_schema','json_schema':{'name':'comfort_'+kind,'strict':True,'schema':spec.schema()}},
        'messages':[{'role':'system','content':prompt},{'role':'user','content':content}]})
    inference_seconds=time.perf_counter()-start
    if not isinstance(response,dict) or not response.get('choices') or response['choices'][0].get('finish_reason')!='stop':
        raise ValueError('Incomplete model response.')
    start=time.perf_counter()
    decoded=json.loads(response['choices'][0]['message']['content'])
    result=validate(decoded)
    validation_seconds=time.perf_counter()-start
    checkpoint()
    raw_usage=response.get('usage',{})
    usage={k:v for k,v in raw_usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens') and type(v) is int and v>=0} if isinstance(raw_usage,dict) else {}
    usage.update(model_setup_seconds=model_setup_seconds,inference_seconds=inference_seconds,validation_seconds=validation_seconds)
    return result,{**provenance,'usage':usage}
