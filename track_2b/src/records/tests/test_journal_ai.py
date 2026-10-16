import json
from datetime import timedelta
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch
from django.db import connection, DatabaseError, IntegrityError, transaction
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from records import journal, journal_ai
from records.models import AssistantTask, JournalAIProposal, JournalAIReview, JournalAIRequest, JournalEvent, JournalDraft, JournalHistory
from . import test_backend


class JournalAITests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in
    upload=test_backend.BackendTests.upload

    def complete(self,item,token,respond=None):
        config={'model':'swiss-ai/Apertus-v1.5-8B','base':'http://inference:8080/v1','request_timeout':90,'key':''}
        with patch('intelligence.trial.configuration',return_value=config), patch('intelligence.trial.available_models'), \
             patch('intelligence.trial.request_json',side_effect=respond or (lambda *args,**kwargs:self.model_response(item))):
            return journal_ai.process_one(item.task_id,token)

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

    @skipUnless(connection.vendor=='postgresql','PostgreSQL history, trigger and FK lifecycle')
    def test_authenticated_accept_publish_preserves_narrative_history_and_draft_identity(self):
        draft=self.saved_draft()
        response=self.client.post(self.base+'journal/ai/requests/',json.dumps({'draft_revision':draft.revision}),content_type='application/json')
        self.assertEqual(response.status_code,202,response.content)
        item=JournalAIRequest.objects.get(pk=response.json()['id'])
        token='00000000-0000-0000-0000-000000000001'
        AssistantTask.objects.filter(pk=item.task_id).update(state='processing',lease_token=token,lease_expires_at=timezone.now()+timedelta(minutes=5))
        self.assertEqual(self.complete(item,token),'completed')
        item.refresh_from_db()
        self.assertEqual(item.input_snapshot,'')
        route=self.base+f'journal/ai/requests/{item.pk}/'
        proposal=self.client.get(route).json()['proposal']
        self.assertEqual(JournalEvent.objects.count(),0)
        response=self.client.post(route,json.dumps({'outcome':'accepted','fields':proposal['fields']}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        draft.refresh_from_db()
        self.assertEqual(draft.revision,2)
        self.assertEqual(draft.fields['description'],proposal['fields']['description'])
        self.assertEqual(draft.fields['severity'],'6')
        values={'category':draft.fields['category'],'description':draft.fields['description'],
            'occurrence':{'precision':'unknown','year':None,'month':None,'day':None},
            'time':None,'timezone':'Africa/Nairobi','fold':None,'severity':6,'concern_id':None}
        response=self.client.post(self.base+'journal/',json.dumps({'values':values,'expected_revision':0,'draft_revision':draft.revision}),content_type='application/json')
        self.assertEqual(response.status_code,201,response.content)
        event=JournalEvent.objects.get(pk=response.json()['id'])
        self.assertEqual(event.description,proposal['fields']['description'])
        self.assertFalse(JournalDraft.objects.filter(pk=draft.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.draft_id,draft.pk)
        self.assertTrue(self.client.get(route).json()['stale'])
        history=JournalHistory.objects.get(event=event,revision=1)
        self.assertEqual(history.snapshot['description'],event.description)
        with self.assertRaises(DatabaseError),transaction.atomic():
            JournalHistory.objects.filter(pk=history.pk).update(snapshot={})

    def test_pending_request_does_not_prevent_discard_or_allow_generation_afterwards(self):
        item,token=self.queued()
        draft=JournalDraft.objects.get(pk=item.draft_id)
        original_id=draft.pk
        journal.discard_draft(self.alice,self.workspace.pk,draft.revision)
        item.refresh_from_db()
        self.assertEqual(item.draft_id,original_id)
        self.assertFalse(JournalDraft.objects.filter(pk=original_id).exists())
        self.assertEqual(self.complete(item,token),'failed')
        self.assertFalse(JournalAIProposal.objects.filter(request=item).exists())
        self.assertTrue(journal_ai.request_payload(item)['stale'])

    def test_draft_advanced_during_inference_keeps_writing_and_allows_request_cleanup(self):
        item,token=self.queued()
        def respond(*args,**kwargs):
            draft=JournalDraft.objects.get(pk=item.draft_id)
            journal.save_draft(self.alice,self.workspace.pk,{**draft.fields,'description':'New fictional writing that must survive.'},draft.revision,None,0)
            return self.model_response(item)
        self.assertEqual(self.complete(item,token,respond),'completed')
        item.refresh_from_db()
        self.assertEqual(item.input_snapshot,'')
        self.assertTrue(journal_ai.request_payload(item)['stale'])
        fields=JournalAIProposal.objects.get(request=item).fields
        with self.assertRaises(journal.services.Conflict):
            journal_ai.review(self.alice,self.workspace.pk,item.pk,'accepted',fields)
        self.assertEqual(JournalDraft.objects.get(pk=item.draft_id).fields['description'],'New fictional writing that must survive.')
        journal_ai.review(self.alice,self.workspace.pk,item.pk,'rejected')
        self.assertIsNone(JournalAIProposal.objects.get(request=item).fields)

    def test_draft_deleted_during_inference_keeps_historical_request_and_can_reject(self):
        item,token=self.queued()
        def respond(*args,**kwargs):
            draft=JournalDraft.objects.get(pk=item.draft_id)
            journal.discard_draft(self.alice,self.workspace.pk,draft.revision)
            return self.model_response(item)
        self.assertEqual(self.complete(item,token,respond),'completed')
        fields=JournalAIProposal.objects.get(request=item).fields
        with self.assertRaises(journal.services.Conflict):
            journal_ai.review(self.alice,self.workspace.pk,item.pk,'accepted',fields)
        journal_ai.review(self.alice,self.workspace.pk,item.pk,'rejected')
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_digest_verifies_preserved_original_independently_of_cleared_snapshot(self):
        item,token=self.queued()
        self.assertEqual(self.complete(item,token),'completed')
        item.refresh_from_db()
        proposal=JournalAIProposal.objects.get(request=item)
        self.assertEqual(item.input_snapshot,'')
        self.assertEqual(journal_ai.original_description(item,proposal),proposal.fields['description'])
        altered=SimpleNamespace(fields={**proposal.fields,'description':'Rewritten by a model.'})
        with self.assertRaises(journal.services.Conflict): journal_ai.original_description(item,altered)
        with self.assertRaises(ValueError):
            journal_ai.review(self.alice,self.workspace.pk,item.pk,'accepted',altered.fields)
        self.assertEqual(JournalDraft.objects.get(pk=item.draft_id).revision,1)

    def test_expired_lease_cannot_start_inference_or_publish_a_proposal(self):
        item,token=self.queued()
        AssistantTask.objects.filter(pk=item.task_id).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        with patch('intelligence.trial.request_json') as infer:
            self.assertEqual(journal_ai.process_one(item.task_id,token),'failed')
            infer.assert_not_called()
        self.assertFalse(JournalAIProposal.objects.exists())

    def test_lease_expiring_during_inference_discards_output(self):
        item,token=self.queued()
        def respond(*args,**kwargs):
            AssistantTask.objects.filter(pk=item.task_id).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
            return self.model_response(item)
        self.assertEqual(self.complete(item,token,respond),'failed')
        item.task.refresh_from_db()
        self.assertEqual(item.task.safe_error_code,'worker_lease_expired')
        self.assertFalse(JournalAIProposal.objects.exists())
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_cleanup_progresses_past_cleared_prefix_and_inflight_requests(self):
        draft=self.saved_draft()
        past=timezone.now()-timedelta(days=8)
        items=[]
        for index in range(6):
            with patch('records.journal_ai.RETENTION',timedelta(days=-1-index)):
                item=journal_ai.create(self.alice,self.workspace.pk,draft.revision)
            if index==5:
                AssistantTask.objects.filter(pk=item.task_id).update(state='processing',lease_token='00000000-0000-0000-0000-000000000001',lease_expires_at=timezone.now()+timedelta(minutes=5))
            else:
                AssistantTask.objects.filter(pk=item.task_id).update(state='failed',finished_at=past,safe_error_code='synthetic_test')
            items.append(item)
        self.assertEqual(journal_ai.expire_old(batch_size=2),2)
        self.assertEqual(journal_ai.expire_old(batch_size=2),2)
        self.assertEqual(journal_ai.expire_old(batch_size=2),1)
        self.assertEqual(journal_ai.expire_old(batch_size=2),0)
        self.assertEqual(JournalAIRequest.objects.filter(snapshot_released_at__isnull=False).count(),5)
        items[5].refresh_from_db()
        self.assertNotEqual(items[5].input_snapshot,'')
        self.assertEqual(JournalEvent.objects.count(),0)

    def test_share_recipient_cannot_list_retrieve_or_review_private_proposals(self):
        from records import services, continuity
        version=self.upload()
        packet=services.create_packet(self.alice,self.workspace.pk,'Fictional test only',[str(version.pk)])
        continuity.create_grant(self.alice,self.workspace.pk,'read',packet.revisions.get().pk,self.bob.pk,'Fictional test',60)
        item,token=self.queued()
        self.assertEqual(self.complete(item,token),'completed')
        self.sign_in(self.bob)
        route=self.base+f'journal/ai/requests/{item.pk}/'
        self.assertEqual(self.client.get(self.base+'journal/ai/requests/').status_code,404)
        self.assertEqual(self.client.get(route).status_code,404)
        self.assertEqual(self.client.post(route,json.dumps({'outcome':'rejected'}),content_type='application/json').status_code,404)
        self.assertEqual(JournalAIReview.objects.count(),0)

    @skipUnless(connection.vendor=='postgresql','Immutable historical binding and insert scope')
    def test_postgres_historical_identity_digest_and_cross_workspace_guards(self):
        item,token=self.queued()
        for changes in ({'workspace_id':self.bob_workspace.pk},{'draft_revision':2},{'draft_id':self.bob_workspace.pk},
                        {'input_sha256':'0'*64},{'input_snapshot':'A substituted narrative.'}):
            with self.assertRaises(IntegrityError),transaction.atomic():
                JournalAIRequest.objects.filter(pk=item.pk).update(**changes)
        self.assertEqual(self.complete(item,token),'completed')
        item.refresh_from_db()
        with self.assertRaises(IntegrityError),transaction.atomic():
            JournalAIRequest.objects.filter(pk=item.pk).update(input_snapshot='Restored after release.')
        task=AssistantTask.objects.create(workspace=self.bob_workspace,requested_by=self.bob,kind='journal_interpretation',parameters={})
        with self.assertRaises(IntegrityError),transaction.atomic():
            JournalAIRequest.objects.create(workspace=self.bob_workspace,task=task,requested_by=self.bob,
                draft_id=item.draft_id,draft_revision=1,input_snapshot='Foreign',input_sha256='0'*64,
                reference_at=timezone.now(),reference_timezone='UTC',expires_at=timezone.now()+timedelta(days=1))

    @skipUnless(connection.vendor=='postgresql','Restricted runtime database role')
    def test_runtime_role_can_accept_and_publish_with_immutable_history(self):
        from identity.db_roles import configure_runtime_permissions
        configure_runtime_permissions(connection)
        with connection.cursor() as cursor: cursor.execute('SET LOCAL ROLE continuity_app')
        try:
            self.test_authenticated_accept_publish_preserves_narrative_history_and_draft_identity()
        finally:
            with connection.cursor() as cursor: cursor.execute('RESET ROLE')
