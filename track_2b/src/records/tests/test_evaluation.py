import json
from django.test import SimpleTestCase
from intelligence import benchmark


class FrozenEvaluationTests(SimpleTestCase):
    def setUp(self):
        self.suite, self.documents, self.digest = benchmark.load_fixture()

    def test_corpus_baseline_and_abstention_denominators(self):
        self.assertEqual(len(self.suite['queries']),20)
        self.assertEqual(len(self.suite['overviews']),10)
        self.assertEqual(benchmark.keyword_results('Fictional medicine A',self.documents),['d03','d04'])
        self.assertEqual(benchmark.retrieval_scores([],[])['correct_abstention'],True)
        self.assertEqual(benchmark.retrieval_scores(['d01'],[])['recall_at_5'],0)
        self.assertEqual(benchmark.retrieval_scores(['d02'],['d01','d02'])['reciprocal_rank'],0.5)

    def test_wrong_attribution_and_fabricated_quote_fail_production_validator(self):
        case=self.suite['queries'][0]
        task,context,sources=benchmark.context_for(case,self.documents)
        payload={'matches':[{'source_id':'s1','reason':'Haemoglobin report',
            'citations':[{'chunk_id':'s2-c0','quote':sources[1].chunks[0]['text']}]}],'abstained':False}
        self.assertFalse(benchmark.grade(case,payload,sources,task)['format_and_quotes_valid'])
        payload['matches'][0]['citations']=[{'chunk_id':'s1-c0','quote':'Fabricated result'}]
        self.assertFalse(benchmark.grade(case,payload,sources,task)['format_and_quotes_valid'])

    def test_valid_quote_does_not_by_itself_establish_semantic_safety(self):
        case=self.suite['overviews'][1]
        task,context,sources=benchmark.context_for(case,self.documents)
        payload={'items':[{'text':'Confirmed asthma diagnosis.',
            'citations':[{'chunk_id':'s1-c0','quote':sources[0].chunks[0]['text']}]}],'abstained':False}
        grading=benchmark.grade(case,payload,sources,task)
        self.assertTrue(grading['format_and_quotes_valid'])
        self.assertFalse(grading['information_screen_passed'])

    def test_sources_first_serialization_preserves_content_and_stable_query_prefix(self):
        from records.assistant import serialize_context
        case=self.suite['queries'][0]
        _,context,_=benchmark.context_for(case,self.documents)
        first=serialize_context(context)
        context['request']={'query':'different question'}
        second=serialize_context(context)
        self.assertEqual(first.split(', "request":')[0],second.split(', "request":')[0])
        self.assertEqual(json.loads(second),context)

    def test_bounded_generation_contract_rejects_oversized_search_and_overview(self):
        from records.assistant import validate_response
        case=self.suite['queries'][0]
        task,_,sources=benchmark.context_for(case,self.documents)
        match={'source_id':'s1','reason':'x'*121,'citations':[{'chunk_id':'s1-c0','quote':'CBC report.'}]}
        with self.assertRaises(ValueError): validate_response(task,{'matches':[match],'abstained':False},sources)
        match['reason']='Blood count report'
        with self.assertRaises(ValueError): validate_response(task,{'matches':[match]*4,'abstained':False},sources)
        overview=self.suite['overviews'][1]
        task,_,sources=benchmark.context_for(overview,self.documents)
        item={'text':'x'*301,'citations':[{'chunk_id':'s1-c0','quote':sources[0].chunks[0]['text']}]}
        with self.assertRaises(ValueError): validate_response(task,{'items':[item],'abstained':False},sources)
