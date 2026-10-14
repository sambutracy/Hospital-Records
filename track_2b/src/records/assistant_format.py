"""Local output grammar; evidence and authority still require independent checks."""
def output_format(task,sources):
    labels=[source.source_label for source in sources]
    chunks=[chunk['id'] for source in sources for chunk in source.chunks]
    citation={'type':'object','additionalProperties':False,'required':['chunk_id','quote'],
        'properties':{'chunk_id':{'type':'string','enum':chunks},'quote':{'type':'string','minLength':1,'maxLength':500}}}
    citations={'type':'array','maxItems':4,'items':citation}
    if task.kind=='search':
        collection='matches'
        search_citation={**citation,'properties':{**citation['properties'],'quote':{'type':'string','minLength':1,'maxLength':200}}}
        item={'type':'object','additionalProperties':False,'required':['source_id','reason','citations'],
            'properties':{'source_id':{'type':'string','enum':labels},'reason':{'type':'string','minLength':1,'maxLength':120},
                'citations':{**citations,'minItems':1,'maxItems':1,'items':search_citation}}}
        properties={collection:{'type':'array','maxItems':3,'items':item}}
    elif task.kind=='packet_overview':
        collection='items'
        overview_citation={**citation,'properties':{**citation['properties'],'quote':{'type':'string','minLength':1,'maxLength':300}}}
        item={'type':'object','additionalProperties':False,'required':['text','citations'],
            'properties':{'text':{'type':'string','minLength':1,'maxLength':300},'citations':{**citations,'minItems':1,'maxItems':2,'items':overview_citation}}}
        properties={collection:{'type':'array','maxItems':4,'items':item}}
    else:
        properties={'definition_id':{'enum':task.parameters['definition_ids']+[None]},'citations':citations}
    properties['abstained']={'type':'boolean'}
    schema={'type':'object','additionalProperties':False,'properties':properties,'required':list(properties)}
    return {'response_format':{'type':'json_schema','json_schema':{'name':'record_assistant','strict':True,'schema':schema}}}
