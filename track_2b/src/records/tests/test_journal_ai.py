import json
from datetime import timedelta
from unittest.mock import patch
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from records import journal, journal_ai
from records.models import AssistantTask, JournalAIProposal, JournalAIReview, JournalAIRequest, JournalEvent
from . import test_backend


class JournalAITests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in

    def saved_draft(self,text='Headache and pain was 6/10. I took medicine, but I do not know its name.'):
        fields={'category':'note','description':text,'precision':'unknown','year':'','month':'','day':'',
            'time':'','timezone':'Africa/Nairobi','fold':'','severity':'','concern_id':''}
        return journal.save_draft(self.alice,self.workspace.pk,fields,0,None,0)

    def queued(self,text=None):
        draft=self.saved_draft(text) if text is not None else self.saved_draft()
        item=journal_ai.create(self.alice,self.workspace.pk,draft.revision)
        token='00000000-0000-0000-0000-000000000001'
        AssistantTask.objects.filter(pk=item.task_id).update(state='processing',lease_token=token,lease_expires_at=timezone.now()+timedelta(minutes=5))
        return item,token

    def model_response(self,request):
        text=request.input_snapshot
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'category':'symptom','occurrence':{'precision':'unknown','year':None,'month':None,'day':None},
            'time':None,'severity':6,'evidence':{'category':{'quote':'Headache'},'severity':{'quote':'6/10'}},
            'unknown':['Medication name'],
            'ambiguities':[],'abstained':False})}}], 'usage':{'prompt_tokens':50,'completion_tokens':80}}

    def test_explicit_request_uses_only_saved_draft_and_returns_unconfirmed_proposal(self):
        item,token=self.queued()
        config={'model':'swiss-ai/Apertus-v1.5-8B','base':'http://inference:8080/v1','request_timeout':90,'key':''}
        with patch('intelligence.trial.configuration',return_value=config), patch('intelligence.trial.available_models'), \
             patch('intelligence.trial.request_json',side_effect=lambda *args,**kwargs:self.model_response(item)) as infer:
            self.assertEqual(journal_ai.process_one(item.task_id,token),'completed')
        self.assertEqual(infer.call_args.args[2]['messages'][1]['content'],item.input_snapshot)
        item.refresh_from_db(); item.task.refresh_from_db()
        self.assertEqual(item.input_snapshot,'')
        self.assertEqual(item.task.result.keys(),{'proposal_id'})
        self.assertEqual(item.task.state,'completed')
        proposal=JournalAIProposal.objects.get(request=item)
        self.assertEqual(proposal.fields['category'],'symptom')
        self.assertEqual(proposal.fields['severity'],'6')
        self.assertEqual(proposal.fields['description'],'Headache and pain was 6/10. I took medicine, but I do not know its name.')
        self.assertEqual(JournalAIReview.objects.count(),0)
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_invalid_severity_evidence_is_rejected(self):
        item,_=self.queued()
        payload=self.model_response(item)['choices'][0]['message']['content']
        decoded=json.loads(payload)
        decoded['severity']=8
        with self.assertRaises(ValueError): journal_ai.validate(decoded,item)

    def test_spelled_out_numeric_severity_is_supported_but_qualitative_intensity_is_not(self):
        item,_=self.queued()
        item.input_snapshot='Fictional test: the headache was six out of ten.'
        payload={'category':'symptom','occurrence':{'precision':'unknown','year':None,'month':None,'day':None},
            'time':None,'severity':6,'evidence':{'category':{'quote':'headache'},'severity':{'quote':'six out of ten'}},
            'unknown':[],'ambiguities':[],'abstained':False}
        self.assertEqual(journal_ai.validate(payload,item)['fields']['severity'],'6')
        payload['evidence']['severity']['quote']='very painful'
        with self.assertRaises(ValueError): journal_ai.validate(payload,item)

    def test_named_month_and_year_preserve_partial_date_precision(self):
        item,_=self.queued('Fictional note: I remember a headache in October 2025, but not the day.')
        payload={'category':'symptom','occurrence':{'precision':'month','year':2025,'month':10,'day':None},
            'time':None,'severity':None,'evidence':{'category':{'quote':'headache'},'occurrence':{'quote':'October 2025'}},
            'unknown':[],'ambiguities':[],'abstained':False}
        fields=journal_ai.validate(payload,item)['fields']
        self.assertEqual((fields['precision'],fields['year'],fields['month'],fields['day']),('month','2025','10',''))

    def test_negated_severity_and_model_added_diagnosis_are_rejected(self):
        text='Fictional note: I did not rate the headache as six out of ten.'
        item,_=self.queued(text)
        payload={'category':'symptom','occurrence':{'precision':'unknown','year':None,'month':None,'day':None},
            'time':None,'severity':6,'evidence':{'category':{'quote':'headache'},'severity':{'quote':'six out of ten'}},
            'unknown':[],'ambiguities':[],'abstained':False}
        with self.assertRaises(ValueError): journal_ai.validate(payload,item)
        payload['severity']=None
        payload['evidence'].pop('severity')
        payload['diagnosis']='migraine'
        with self.assertRaises(ValueError): journal_ai.validate(payload,item)

    def test_changed_draft_cannot_accept_old_proposal(self):
        item,token=self.queued()
        config={'model':'swiss-ai/Apertus-v1.5-8B','base':'http://inference:8080/v1','request_timeout':90,'key':''}
        with patch('intelligence.trial.configuration',return_value=config), patch('intelligence.trial.available_models'), \
             patch('intelligence.trial.request_json',side_effect=lambda *args,**kwargs:self.model_response(item)):
            self.assertEqual(journal_ai.process_one(item.task_id,token),'completed')
        old=journal.JournalDraft.objects.get(pk=item.draft_id)
        fields={**old.fields,'description':'Changed while Apertus was working.'}
        journal.save_draft(self.alice,self.workspace.pk,fields,old.revision,None,0)
        with self.assertRaises(journal.services.Conflict):
            journal_ai.review(self.alice,self.workspace.pk,item.pk,'accepted',fields)
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_rejection_records_review_and_clears_sensitive_proposal(self):
        item,token=self.queued()
        config={'model':'swiss-ai/Apertus-v1.5-8B','base':'http://inference:8080/v1','request_timeout':90,'key':''}
        with patch('intelligence.trial.configuration',return_value=config), patch('intelligence.trial.available_models'), \
             patch('intelligence.trial.request_json',side_effect=lambda *args,**kwargs:self.model_response(item)):
            self.assertEqual(journal_ai.process_one(item.task_id,token),'completed')
        journal_ai.review(self.alice,self.workspace.pk,item.pk,'rejected')
        proposal=JournalAIProposal.objects.get(request=item)
        self.assertIsNone(proposal.fields)
        self.assertEqual(proposal.evidence,{})
        self.assertEqual(JournalAIReview.objects.get(proposal=proposal).outcome,'rejected')
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_other_patient_cannot_read_request(self):
        item,_=self.queued()
        with self.assertRaises(Http404): journal_ai.get(self.bob,self.workspace.pk,item.pk)
