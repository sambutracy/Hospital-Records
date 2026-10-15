from types import SimpleNamespace
from django.test import SimpleTestCase
from records import local_evidence


class LocalEvidenceTests(SimpleTestCase):
    def task(self,kind='search'):
        return SimpleNamespace(kind=kind,parameters={'query':'Medicine Q'})

    def context(self):
        return {'sources':[{'source_id':'s1','chunks':[
            {'chunk_id':'s1-c0','text':'reported.pdf','origin':'uploaded_filename'},
            {'chunk_id':'s1-c1','text':'Document date: 2025\nMedicine Q was prescribed. Whether taken is unknown.', 'origin':'source_text'}]},
            {'source_id':'s2','chunks':[{'chunk_id':'s2-c0','text':'No history of asthma.', 'origin':'source_text'}]}]}

    def test_query_selects_exact_evidence_and_expands_through_original_chunk(self):
        context,evidence=local_evidence.plan(self.task(),self.context())
        first=evidence['e1']
        self.assertEqual(first['text'],'Medicine Q was prescribed. Whether taken is unknown.')
        self.assertEqual(first['original_chunk_id'],'s1-c1')
        payload=local_evidence.expand(self.task(),{'evidence':['e1'],'abstained':False},evidence)
        self.assertEqual(payload['matches'][0]['citations'],[{'chunk_id':'s1-c1','quote':first['text']}])
        self.assertNotIn('reported.pdf',str(context))

    def test_no_generated_prose_or_unknown_duplicate_identifiers_are_accepted(self):
        _,evidence=local_evidence.plan(self.task(),self.context())
        for payload in ({'evidence':['foreign'],'abstained':False},
            {'evidence':['e1','e1'],'abstained':False}, {'evidence':[],'abstained':False},
            {'evidence':['e1'],'abstained':False,'text':'Invented diagnosis'}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                local_evidence.expand(self.task(),payload,evidence)

    def test_search_rejects_multiple_matches_from_the_same_source(self):
        _,evidence=local_evidence.plan(self.task(),self.context())
        keys=[key for key,item in evidence.items() if item['source_id']=='s1']
        with self.assertRaisesRegex(ValueError,'Duplicate source'):
            local_evidence.expand(self.task(),{'evidence':keys,'abstained':False},evidence)

    def test_overview_is_explicitly_extractive_and_preserves_partial_date(self):
        task=self.task('packet_overview');_,evidence=local_evidence.plan(task,self.context())
        key=next(key for key,item in evidence.items() if item['text']=='Document date: 2025')
        result=local_evidence.expand(task,{'evidence':{'s1':[key],'s2':[]},'abstained':False},evidence)
        self.assertEqual(result['items'][0]['text'],'Document date: 2025')
        self.assertEqual(result['items'][0]['citations'][0]['quote'],'Document date: 2025')

    def test_overview_requires_each_source_key_and_binds_identifiers_to_source(self):
        task=self.task('packet_overview');_,evidence=local_evidence.plan(task,self.context())
        first=next(key for key,item in evidence.items() if item['source_id']=='s1')
        for value in ({'s1':[first]},{'s1':[],'s2':[first]}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                local_evidence.expand(task,{'evidence':value,'abstained':False},evidence)

    def test_large_context_is_bounded_and_retains_multiple_sources(self):
        text='No new diagnosis. '+('Long source content preserving a qualification. '*150)
        original={'sources':[{'source_id':f's{i}','chunks':[{'chunk_id':f's{i}-c0','text':text,'origin':'source_text'}]} for i in range(10)]}
        context,evidence=local_evidence.plan(self.task(),original)
        self.assertLessEqual(sum(len(item['text']) for item in evidence.values()),local_evidence.MAX_TEXT)
        self.assertLessEqual(len(evidence),local_evidence.MAX_EXCERPTS)
        self.assertEqual(len(context['sources']),10)
        for item in evidence.values():self.assertIn(item['text'],text)

    def test_empty_selection_is_an_explicit_abstention(self):
        _,evidence=local_evidence.plan(self.task(),self.context())
        result=local_evidence.expand(self.task(),{'evidence':[],'abstained':True},evidence)
        self.assertEqual(result,{'matches':[],'abstained':True})

    def test_bare_heading_is_not_evidence_but_short_negative_statement_is(self):
        context={'sources':[{'source_id':'s1','chunks':[{'chunk_id':'s1-c0',
            'origin':'source_text','text':'Findings:\nNo allergies.\nHaemoglobin: 12.1 g/dL.'}]}]}
        _,evidence=local_evidence.plan(self.task('packet_overview'),context)
        texts=[item['text'] for item in evidence.values()]
        self.assertNotIn('Findings:',texts)
        self.assertIn('No allergies.',texts)
        self.assertIn('Haemoglobin: 12.1 g/dL.',texts)

    def test_overview_prioritizes_clinical_passages_and_keeps_medication_qualification(self):
        text='Representation type: prescription\nNo real patient data. Not clinically validated.\nMedicine Q 5 mg was prescribed. Whether taken is unknown.'
        context={'sources':[{'source_id':'s1','chunks':[{'chunk_id':'s1-c0','origin':'source_text','text':text}]}]}
        _,evidence=local_evidence.plan(self.task('packet_overview'),context)
        self.assertEqual([item['text'] for item in evidence.values()],[
            'Medicine Q 5 mg was prescribed. Whether taken is unknown.'])

    def test_unrecognized_clinical_vocabulary_retains_narrative_fallback(self):
        text='A longer narrative with unfamiliar vocabulary remains available for source review.'
        context={'sources':[{'source_id':'s1','chunks':[{'chunk_id':'s1-c0','origin':'source_text','text':text}]}]}
        _,evidence=local_evidence.plan(self.task('packet_overview'),context)
        self.assertEqual(next(iter(evidence.values()))['text'],text)

    def test_clinical_narrative_with_administrative_suffix_is_not_discarded(self):
        text='Patient reports a follow-up conversation. No new diagnosis is established. Fixture annotation.'
        context={'sources':[{'source_id':'s1','chunks':[{'chunk_id':'s1-c0','origin':'source_text',
            'text':'Document date: 2026-03-01\n'+text}]}]}
        _,evidence=local_evidence.plan(self.task('packet_overview'),context)
        self.assertIn(text,[item['text'] for item in evidence.values()])
