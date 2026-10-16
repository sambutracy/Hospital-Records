"""Narrow, source-grounded scalar extraction for a private Journal proposal.

No model calls or persistence. A candidate is a literal source span, never a
diagnosis. Ambiguous, negated and conflicting values remain unavailable.
"""
from calendar import month_name
from datetime import date, timedelta
import re


VERSION='journal-source-fields-v1'
NUMBERS={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,
    'seven':7,'eight':8,'nine':9,'ten':10}
SCALE=re.compile(r'(?<![\w.])(?P<value>10|[0-9]|zero|one|two|three|four|five|six|seven|eight|nine|ten)'
    r'\s*(?:/\s*10|out\s+of\s+(?:10|ten))(?!\w)',re.I)
CLOCK=re.compile(r'(?<![\w:])(?:[01][0-9]|2[0-3]):[0-5][0-9](?![\w:])')
DATE=re.compile(r'(?<!\w)\d{4}-\d{2}-\d{2}(?![\w-])')
MONTH=re.compile(r'(?<![\w-])\d{4}-\d{2}(?![\w-])')
NAMED_MONTH=re.compile(r'\b(?:'+'|'.join(month_name[1:])+r')\s+\d{4}\b',re.I)
YEAR=re.compile(r'\b(?:in|during|since|from)\s+(?P<year>\d{4})(?![\w-])',re.I)
RELATIVE=re.compile(r'\b(?:the day before yesterday|yesterday|today)'
    r'(?:\s+(?:morning|afternoon|evening|night))?\b',re.I)
SYMPTOM=r'(?:headache|nausea|pain|cough|dizz\w*|symptoms?|sore throat|discomfort|tired\w*|weak\w*)'
FAMILY=re.compile(r'\b(?:my|our)\s+(?:aunt|uncle|mother|father|sister|brother|child|daughter|son|grandmother|grandfather|partner|friend|husband|wife)'
    r'\s+(?:had|has|have|felt|feels|was|is|gets|got|suffers)\b',re.I)
HYPOTHETICAL=re.compile(r'\b(?:if\s+(?:i|my|a|the)|would\s+(?:get|have|feel)|might\s+(?:get|develop))\b',re.I)
NEGATED_SYMPTOM=re.compile(r'\b(?:no|without|den(?:y|ies)|never(?:\s+(?:had|have|felt|experienced))?|'
    r'not(?:\s+(?:have|having|had|feel|feeling|experience|experiencing))?)'
    r'\s+(?:(?:a|any|the)\s+)?'+SYMPTOM+r'\b',re.I)
DATE_UNCERTAIN=re.compile(r'\b(?:sometime|which day|unsure when|uncertain when|not sure when|'
    r'cannot remember (?:when|the date|the day)|do not know (?:when|the date|the day)|'
    r'unsure (?:of|about) (?:the )?(?:date|onset)|maybe|possibly)\b',re.I)
ADMIN_DATE=re.compile(r'\b(?:document date|report (?:date|issued)|specimen|date of birth|dob|identifier)\b',re.I)


def scope(text,start,end):
    # Keep decimal points inside a sentence; source punctuation is unchanged.
    boundaries=[0]+[m.end() for m in re.finditer(r'[.!?;](?=\s|$)|\n',text)]+[len(text)]
    left=max(x for x in boundaries if x<=start)
    right=min(x for x in boundaries if x>=end)
    return text[left:right]


def non_asserted(context):
    return bool(FAMILY.search(context) or HYPOTHETICAL.search(context) or NEGATED_SYMPTOM.search(context))


def unsupported_category_context(text,item):
    if non_asserted(scope(text,item['start'],item['end'])): return True
    # Check negation adjacent to the exact category quote even when its symptom
    # term is outside the small English context vocabulary above.
    prefix=text[max(0,item['start']-64):item['start']]
    return bool(re.search(r'\b(?:no|without|den(?:y|ies)|never(?:\s+(?:had|have|felt))?|'
        r'not(?:\s+(?:have|had|having|feel|feeling))?)\s+(?:(?:a|any|the)\s+)?$',prefix,re.I))


def evidence(text,match):
    return {'quote':text[match.start():match.end()],'start':match.start(),'end':match.end(),
        'origin':'source_extraction'}


def explicit_severity(quote):
    match=SCALE.search(quote)
    if not match: return None
    raw=match.group('value').casefold()
    return int(raw) if raw.isdigit() else NUMBERS[raw]


def candidates(text,reference_day):
    found={key:[] for key in ('occurrence','time','severity')}
    blocked={key:[] for key in found}

    def add(field,match,value):
        context=scope(text,match.start(),match.end())
        if non_asserted(context):
            blocked[field].append('non_asserted_source'); return
        prefix=text[max(0,match.start()-48):match.start()]
        if field in ('severity','time') and re.search(r'\b(?:not|never|no)\b[^.!?;\n]{0,40}$',prefix,re.I):
            blocked[field].append('negated_source'); return
        if field=='occurrence' and (DATE_UNCERTAIN.search(context) or ADMIN_DATE.search(context)):
            blocked[field].append('uncertain_source'); return
        found[field].append({'value':value,'evidence':evidence(text,match)})

    for match in SCALE.finditer(text): add('severity',match,explicit_severity(match.group()))
    for match in CLOCK.finditer(text): add('time',match,match.group())
    occupied=[]
    for pattern,precision in ((DATE,'day'),(MONTH,'month'),(NAMED_MONTH,'month'),(YEAR,'year'),(RELATIVE,'relative')):
        for match in pattern.finditer(text):
            if any(match.start()<end and match.end()>start for start,end in occupied): continue
            occupied.append(match.span())
            raw=match.group()
            try:
                if precision=='relative':
                    if reference_day is None:
                        blocked['occurrence'].append('reference_date_missing'); continue
                    offset=2 if raw.lower().startswith('the day before yesterday') else 1 if raw.lower().startswith('yesterday') else 0
                    value=reference_day-timedelta(days=offset)
                    resolved={'precision':'day','year':value.year,'month':value.month,'day':value.day}
                elif precision=='day':
                    value=date.fromisoformat(raw)
                    resolved={'precision':'day','year':value.year,'month':value.month,'day':value.day}
                elif precision=='month':
                    if raw[:4].isdigit(): year,month=map(int,raw.split('-'))
                    else:
                        name,year_text=raw.split(); year=int(year_text)
                        month=list(month_name).index(name.title())
                    date(year,month,1)
                    resolved={'precision':'month','year':year,'month':month,'day':None}
                else:
                    year=int(match.group('year')); date(year,1,1)
                    resolved={'precision':'year','year':year,'month':None,'day':None}
            except ValueError:
                blocked['occurrence'].append('invalid_source_date'); continue
            add('occurrence',match,resolved)
    result={}
    for field,items in found.items():
        distinct={str(item['value']) for item in items}
        # A contradictory or explicitly uncertain candidate must not be
        # silently discarded in favour of another convenient value.
        if len(distinct)>1:
            result[field]={'candidate':None,'reason':'conflicting_source'}
        elif blocked[field] and any(reason in ('uncertain_source','invalid_source_date','negated_source') for reason in blocked[field]):
            result[field]={'candidate':None,'reason':blocked[field][0]}
        elif items:
            result[field]={'candidate':items[0],'reason':None}
        else:
            result[field]={'candidate':None,'reason':blocked[field][0] if blocked[field] else 'no_explicit_source'}
    return result


LABELS={'occurrence':'Occurrence date','time':'Exact time','severity':'Severity'}
REASONS={
    'no_explicit_source':'no supported explicit source value; leave unknown or enter it yourself',
    'invalid_source_date':'the source date is not a valid calendar date; confirm it yourself',
    'reference_date_missing':'the trusted reference date is unavailable',
    'non_asserted_source':'the source refers to a negated, hypothetical or other-person observation',
    'negated_source':'the source value is negated; it has not been suggested',
    'uncertain_source':'the source does not establish an unambiguous value',
    'conflicting_source':'the source contains conflicting values; choose the correct context yourself',
    'model_uncertain':'Apertus marked this field uncertain; confirm it yourself',
    'model_source_disagreement':'the model suggestion disagrees with the source; neither was substituted',
    'unsupported_model_value':'the model suggestion has an unsupported format or precision',
    'quote_not_verified':'the model quote could not be verified; that suggestion was omitted',
    'quote_does_not_support_field':'the supplied quote does not support this field; that suggestion was omitted',
    'time_needs_date':'an exact occurrence date is needed before a clock time can be recorded',
    'time_needs_confirmation':'the local clock time needs confirmation for this date and timezone',
    'context_not_asserted':'optional values were not inferred for a note or abstained interpretation',
}


def flag(result,field,reason):
    """Fixed patient-facing explanation and content-free diagnostic labels."""
    item={'field':field,'reason':reason}
    if item not in result['field_abstentions']: result['field_abstentions'].append(item)
    if LABELS[field] not in result['unknown']: result['unknown'].append(LABELS[field])
    message=LABELS[field]+': '+REASONS[reason]+'.'
    if message not in result['ambiguities']: result['ambiguities'].append(message)


def normalize(payload,narrative,reference_day,zone,base_fields,fail):
    keys={'category','occurrence','time','severity','evidence','unknown','ambiguities','abstained'}
    if not isinstance(payload,dict) or set(payload)!=keys or type(payload['abstained']) is not bool:
        raise fail('output_schema_invalid')
    if payload['category'] not in ('note','symptom'): raise fail('category_unsupported')
    for key in ('unknown','ambiguities'):
        values=payload[key]
        if not isinstance(values,list) or len(values)>8 or any(not isinstance(x,str) or len(x)>120 for x in values):
            raise fail('output_schema_invalid')
    occurrence=payload['occurrence']
    if not isinstance(occurrence,dict) or set(occurrence)!={'precision','year','month','day'}:
        raise fail('output_schema_invalid')
    evidence_values=payload['evidence']
    if not isinstance(evidence_values,dict) or set(evidence_values)-{'category','occurrence','time','severity'}:
        raise fail('output_schema_invalid')
    checked={}; invalid=set()
    for field,item in evidence_values.items():
        if not isinstance(item,dict) or set(item)!={'quote'}: raise fail('output_schema_invalid')
        quote=item['quote']
        if not isinstance(quote,str) or not quote or quote not in narrative:
            if field=='category':
                raise fail('citation_invalid',field,'quote_not_in_source' if isinstance(quote,str) and quote else 'quote_missing_or_invalid')
            invalid.add(field); continue
        start=narrative.index(quote)
        checked[field]={'quote':quote,'start':start,'end':start+len(quote),'origin':'apertus_quote'}
    if 'category' not in checked: raise fail('citation_invalid','category','required_quote_missing')
    category=payload['category']
    if category=='symptom' and unsupported_category_context(narrative,checked['category']):
        raise fail('category_context_unsupported','category','non_asserted_source')
    if payload['abstained'] and category!='note': raise fail('output_semantics_invalid')
    fields={**base_fields,'category':category,'precision':'unknown','year':'','month':'','day':'',
        'time':'','fold':'','timezone':zone,'severity':'','description':narrative}
    result={'fields':fields,'evidence':{'category':checked['category']},'unknown':[],
        'ambiguities':[],'field_abstentions':[],'source_normalized_fields':[]}
    source=candidates(narrative,reference_day)
    model_values={'occurrence':occurrence,'time':payload['time'],'severity':payload['severity']}
    uncertain=set()
    # Never display arbitrary model-written medical claims from free-text
    # uncertainty lists. They can only lower confidence in a named field.
    for text in payload['unknown']+payload['ambiguities']:
        if re.search(r'\b(?:date|onset|when|day)\b',text,re.I): uncertain.add('occurrence')
        if re.search(r'\b(?:time|clock)\b',text,re.I): uncertain.add('time')
        if re.search(r'\b(?:severity|intensity|rating)\b',text,re.I): uncertain.add('severity')
    for field in ('occurrence','time','severity'):
        candidate=source[field]['candidate']
        value=model_values[field]
        if category!='symptom' or payload['abstained']:
            flag(result,field,'context_not_asserted'); continue
        if field in invalid:
            flag(result,field,'quote_not_verified'); continue
        if field in uncertain:
            flag(result,field,'model_uncertain'); continue
        if candidate is None:
            flag(result,field,source[field]['reason']); continue
        expected=candidate['value']
        if field=='occurrence':
            if value['precision'] not in ('unknown','year','month','day') or (
                    value['precision']=='unknown' and any(value[key] is not None for key in ('year','month','day'))):
                flag(result,field,'unsupported_model_value'); continue
            if value['precision']!='unknown' and (value['precision']!=expected['precision'] or any(
                    value[key] is not None and (type(value[key]) is not int or value[key]!=expected[key])
                    for key in ('year','month','day'))):
                flag(result,field,'model_source_disagreement'); continue
        elif value is not None:
            if (field=='severity' and (type(value) is not int or not 0<=value<=10)) or (
                    field=='time' and (not isinstance(value,str) or not CLOCK.fullmatch(value))):
                flag(result,field,'unsupported_model_value'); continue
            if value!=expected:
                flag(result,field,'model_source_disagreement'); continue
        if field in checked and candidate['evidence']['quote'] not in checked[field]['quote']:
            flag(result,field,'quote_does_not_support_field'); continue
        if field=='time' and fields['precision']!='day':
            flag(result,field,'time_needs_date'); continue
        if field=='occurrence':
            fields.update(precision=expected['precision'],year=str(expected['year'] or ''),
                month=str(expected['month'] or ''),day=str(expected['day'] or ''))
        else: fields[field]=str(expected)
        result['evidence'][field]=candidate['evidence']
        result['source_normalized_fields'].append(field)
        if field not in checked or value is None or (field=='occurrence' and value['precision']=='unknown'):
            result['ambiguities'].append(LABELS[field]+': copied from an explicit source span; confirm before applying.')
    result['discarded_model_fields']=[]
    for field in ('occurrence','time','severity'):
        offered=(occurrence['precision']!='unknown' or any(occurrence[key] is not None for key in ('year','month','day'))
            if field=='occurrence' else model_values[field] is not None)
        if field not in result['evidence'] and (field in invalid or offered):
            result['discarded_model_fields'].append(field)
    return result
