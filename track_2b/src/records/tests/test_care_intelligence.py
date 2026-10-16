from datetime import timedelta
import hashlib
import json
from unittest import skipUnless
from unittest.mock import patch
from django.db import connection, DatabaseError, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from identity.models import AccessCapability
from identity.db_roles import configure_runtime_permissions
from records import assistant_worker, care_intelligence as ai, care_services, journal, medications, services, continuity
from records.models import (AssistantTask, CareAIEvidence, CareAIReview, JournalHistory, JournalEvent, SourceVersion,
    TextExtraction, CareEpisode, ShareGrant)
from . import test_backend


@skipUnless(connection.vendor=='postgresql','PostgreSQL immutable history and cross-source guards')
@override_settings(CARE_INTELLIGENCE_ENABLED=True)
class CareIntelligenceTests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in
    upload=test_backend.BackendTests.upload

    def seed_evidence(self):
        self.event=journal.save(self.alice,self.workspace.pk,{'category':'symptom','description':'Fictional headache, 6/10, no nausea.',
            'occurrence':{'precision':'day','year':2026,'month':10,'day':12},'time':None,'timezone':'Africa/Nairobi','fold':None,'severity':6,'concern_id':None},0)
        self.version=self.upload('Fictional consultation: Return for review on 2026-10-20. The time is not stated.')
        pages=[{'page':1,'text':'Fictional consultation: Return for review on 2026-10-20. The time is not stated.'}]
        TextExtraction.objects.create(workspace=self.workspace,source_version=self.version,pages=pages,extractor_version='synthetic-test-v1',text_sha256=hashlib.sha256(json.dumps(pages).encode()).hexdigest())
        self.episode=CareEpisode.objects.create(workspace=self.workspace,title='Fictional care grouping',created_by=self.alice)
        self.med=medications.save(self.alice,self.workspace.pk,{'medicine_name':'Fictional Medicine A','dose':'As written in fictional report','frequency':'Unknown','route':'',
            'instructions':'Details not supplied.','use_status':'reported_prescribed','visit_date':{'precision':'month','year':2026,'month':10,'day':None},
            'episode_id':str(self.episode.pk),'source_version_id':str(self.version.pk)},0)
        self.concern=care_services.save(self.alice,self.workspace.pk,'concerns',{'title':'Fictional unresolved concern','description':'No confirmed cause.',
            'kind':'issue','certainty':'unconfirmed','onset':{'precision':'year','year':2026,'month':None,'day':None}},0)

    def request(self,selected=None):
        keys=selected if selected is not None else [{'kind':kind,'id':str(item.pk),'revision':getattr(item,'revision',1)} for kind,item in
            [('journal',self.event),('document',self.version),('medication',self.med),('concern',self.concern),('episode',self.episode)]]
        response=self.client.post(self.base+'care-ai/tasks/',json.dumps({'kind':'history_exploration','from':'2026-10-01','to':'2026-10-31',
            'include_undated':True,'selected':keys}),content_type='application/json')
        self.assertEqual(response.status_code,202,response.content)
        return AssistantTask.objects.get(pk=response.json()['id'])

    def complete(self,task,items=None,hook=None):
        token='00000000-0000-0000-0000-000000000001'
        AssistantTask.objects.filter(pk=task.pk).update(state='processing',lease_token=token,lease_expires_at=timezone.now()+timedelta(minutes=5),started_at=timezone.now())
        evidence,metadata,_=ai.snapshots(task)
        def respond(*args,**kwargs):
            if hook: hook()
            result={'items':items if items is not None else [{'evidence_id':row.label,'quote':row.text[:150],'category':'source_excerpt'} for row in evidence],
                'limitations':['selected_evidence_only'],'abstained':False}
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}], 'usage':{'prompt_tokens':100,'completion_tokens':50}}
        with patch('intelligence.trial.configuration',return_value={'base':'http://inference:8080/v1','model':'local-apertus','key':'','request_timeout':300}),\
             patch('intelligence.trial.available_models'),patch('intelligence.trial.request_json',side_effect=respond) as infer:
            result=assistant_worker.process_one(task.pk,token)
        return result,infer

    def test_source_selected_history_worker_review_journey_and_unchanged_domain_records(self):
        self.seed_evidence(); task=self.request()
        self.assertEqual(task.care_evidence.count(),5)
        journal_ref=task.care_evidence.get(kind='journal')
        self.assertEqual(journal_ref.target_id,JournalHistory.objects.get(event=self.event).pk)
        result,infer=self.complete(task)
        self.assertEqual(result,'completed'); self.assertEqual(infer.call_count,1)
        task.refresh_from_db()
        self.assertEqual(len(task.result['items']),5)
        self.assertEqual(next(item['source']['use_status'] for item in task.result['items'] if item['source']['kind']=='medication'),'reported_prescribed')
        self.assertEqual(next(item['source']['occurrence']['precision'] for item in task.result['items'] if item['source']['kind']=='concern'),'year')
        route=self.base+f'care-ai/tasks/{task.pk}/'
        self.assertEqual(self.client.get(route)['Cache-Control'],'no-store, private')
        response=self.client.post(route+'review/',json.dumps({'outcome':'kept'}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(len(response.json()['review']['planning_draft']),5)
        self.assertEqual(JournalEvent.objects.count(),1); self.event.refresh_from_db(); self.assertEqual(self.event.revision,1)
        self.assertEqual(ShareGrant.objects.count(),0)

    def test_frozen_consultation_followup_worker_and_edited_private_draft(self):
        self.seed_evidence()
        packet=services.create_packet(self.alice,self.workspace.pk,'Fictional follow-up',[str(self.version.pk)])
        task=ai.create(self.alice,self.workspace.pk,{'kind':'followup_actions','packet_id':str(packet.pk)})
        result,_=self.complete(task,[{'evidence_id':'e1','quote':'Return for review on 2026-10-20.','category':'documented_followup'}])
        self.assertEqual(result,'completed')
        response=self.client.post(self.base+f'care-ai/tasks/{task.pk}/review/',json.dumps({'outcome':'edited','texts':['Ask the clinic to confirm the review time.']}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        draft=response.json()['review']['planning_draft'][0]
        self.assertTrue(draft['patient_edited']); self.assertIn('Return for review on 2026-10-20.',draft['citations'][0]['quote'])
        self.assertEqual(task.packet_revision_id,packet.revisions.get().pk)
        self.assertEqual(ShareGrant.objects.count(),0)

    def test_live_medication_changes_do_not_rewrite_frozen_evidence(self):
        self.seed_evidence(); task=self.request()
        before=task.care_evidence.get(kind='medication').body
        data=medications.values(self.med); data['medicine_name']='New fictional medicine name'
        medications.save(self.alice,self.workspace.pk,data,1,self.med.pk)
        self.assertEqual(self.complete(task)[0],'completed')
        self.assertEqual(task.care_evidence.get(kind='medication').body,before)

    def test_cross_patient_and_packet_share_recipient_cannot_retrieve_or_review(self):
        self.seed_evidence(); task=self.request(); self.assertEqual(self.complete(task)[0],'completed')
        packet=services.create_packet(self.alice,self.workspace.pk,'Fictional share',[str(self.version.pk)])
        continuity.create_grant(self.alice,self.workspace.pk,'read',packet.revisions.get().pk,self.bob.pk,'Fictional test',60)
        self.sign_in(self.bob)
        for path in ('status/',f'tasks/{task.pk}/','tasks/?kind=history_exploration'):
            self.assertEqual(self.client.get(self.base+'care-ai/'+path).status_code,404)
        self.assertEqual(self.client.post(self.base+f'care-ai/tasks/{task.pk}/review/',json.dumps({'outcome':'kept'}),content_type='application/json').status_code,404)
        self.assertEqual(CareAIReview.objects.count(),0)

    def test_new_private_kinds_are_excluded_from_generic_assistant_api(self):
        self.seed_evidence(); task=self.request()
        self.assertEqual(self.client.get(self.base+'assistant/tasks/').json()['tasks'],[])
        self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,404)

    def test_invalid_citations_fail_without_retry_and_without_result(self):
        self.seed_evidence(); task=self.request()
        result,infer=self.complete(task,[{'evidence_id':'e999','quote':'Invented clinical conclusion','category':'source_excerpt'}])
        self.assertEqual(result,'failed'); self.assertEqual(infer.call_count,1)
        task.refresh_from_db(); self.assertIsNone(task.result); self.assertEqual(task.safe_error_code,'invalid_or_unsupported_output')

    def test_lease_and_live_medication_revocation_discard_model_output(self):
        self.seed_evidence(); task=self.request()
        def revoke(): AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_medications').update(revoked_at=timezone.now())
        self.assertEqual(self.complete(task,hook=revoke)[0],'failed')
        task.refresh_from_db(); self.assertIsNone(task.result); self.assertEqual(task.safe_error_code,'authority_unavailable')
        self.assertEqual(self.client.get(self.base+f'care-ai/tasks/{task.pk}/').status_code,404)

    def test_changed_revision_out_of_range_empty_and_duplicate_selection_rejected(self):
        self.seed_evidence()
        for keys,expected in (([],400),([{'kind':'journal','id':str(self.event.pk),'revision':2}],409),
                ([{'kind':'journal','id':str(self.event.pk),'revision':1}]*2,400),
                ([{'kind':'journal','id':str(self.bob_workspace.pk),'revision':1}],404)):
            response=self.client.post(self.base+'care-ai/tasks/',json.dumps({'kind':'history_exploration','from':'2026-10-01','to':'2026-10-31','include_undated':True,'selected':keys}),content_type='application/json')
            self.assertEqual(response.status_code,expected,response.content)
        self.assertEqual(AssistantTask.objects.count(),0)

    def test_candidates_exclude_drafts_and_only_browse_selected_range(self):
        self.seed_evidence()
        response=self.client.get(self.base+'care-ai/candidates/?from=2026-10-01&to=2026-10-31&include_undated=true')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual({row['kind'] for row in response.json()['items']},{'journal','document','medication','concern','episode'})
        dated=self.client.get(self.base+'care-ai/candidates/?from=2020-01-01&to=2020-01-31&include_undated=false').json()
        self.assertEqual(dated['items'],[])

    def test_unreadable_documents_preflight_without_inference(self):
        self.seed_evidence(); other=self.upload('Another fictional file without extraction')
        packet=services.create_packet(self.alice,self.workspace.pk,'Missing report',[str(other.pk)])
        with self.assertRaises(ValueError): ai.create(self.alice,self.workspace.pk,{'kind':'followup_actions','packet_id':str(packet.pk)})
        self.assertEqual(AssistantTask.objects.count(),0)

    def test_feature_gate_and_csrf(self):
        self.seed_evidence()
        with override_settings(CARE_INTELLIGENCE_ENABLED=False):
            self.assertFalse(self.client.get(self.base+'care-ai/status/').json()['enabled'])
            self.assertEqual(self.client.get(self.base+'care-ai/candidates/?from=2026-10-01&to=2026-10-31').status_code,404)
        client=Client(enforce_csrf_checks=True); self.sign_in(self.alice,client)
        self.assertEqual(client.post(self.base+'care-ai/tasks/',json.dumps({'kind':'history_exploration'}),content_type='application/json').status_code,403)

    def test_runtime_role_snapshots_and_review_are_immutable(self):
        self.seed_evidence(); configure_runtime_permissions(connection)
        with connection.cursor() as cursor: cursor.execute('SET LOCAL ROLE continuity_app')
        try:
            task=self.request(); self.assertEqual(self.complete(task)[0],'completed')
            ai.review(self.alice,self.workspace.pk,task.pk,'kept')
            with self.assertRaises(DatabaseError),transaction.atomic(): task.care_evidence.update(body='changed')
            with self.assertRaises(DatabaseError),transaction.atomic(): CareAIReview.objects.filter(task=task).update(outcome='rejected')
        finally:
            with connection.cursor() as cursor: cursor.execute('RESET ROLE')

    def test_expired_care_worker_lease_discards_output(self):
        self.seed_evidence(); task=self.request()
        def expire(): AssistantTask.objects.filter(pk=task.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.complete(task,hook=expire)[0],'failed')
        task.refresh_from_db(); self.assertIsNone(task.result); self.assertEqual(task.safe_error_code,'worker_lease_expired')

    def test_model_cannot_turn_a_noninstruction_into_a_followup_action(self):
        self.seed_evidence()
        packet=services.create_packet(self.alice,self.workspace.pk,'Fictional follow-up',[str(self.version.pk)])
        task=ai.create(self.alice,self.workspace.pk,{'kind':'followup_actions','packet_id':str(packet.pk)})
        self.assertEqual(self.complete(task,[{'evidence_id':'e1','quote':'The time is not stated.','category':'documented_followup'}])[0],'failed')
        task.refresh_from_db(); self.assertIsNone(task.result)
