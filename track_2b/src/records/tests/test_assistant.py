from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import uuid
from unittest import skipUnless
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from identity.models import AccessCapability, PatientWorkspace
from identity.services import resolve_verified_identity
from records import assistant, assistant_worker, services, storage, worker
from records.models import AssistantSource, AssistantTask, ConsultationPacket, TextExtraction
from records.tests.test_backend import pdf, VALUES


class AssistantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice=resolve_verified_identity('https://test.example/issuer','assistant-alice','Alice')
        cls.bob=resolve_verified_identity('https://test.example/issuer','assistant-bob','Bob')
        cls.workspace=PatientWorkspace.objects.get(subject_patient__person=cls.alice.person)
        cls.bob_workspace=PatientWorkspace.objects.get(subject_patient__person=cls.bob.person)

    def setUp(self):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings=override_settings(PRIVATE_STORAGE_ROOT=Path(directory.name))
        settings.enable()
        self.addCleanup(settings.disable)
        self.sign_in(self.alice)
        self.base=f'/api/workspaces/{self.workspace.pk}/'
        self.alpha=self.source(self.alice,self.workspace,'CBC report at Fictional Cedar Clinic. Document date September 2026.','cbc-report.pdf')
        self.beta=self.source(self.alice,self.workspace,'Ultrasound report at Fictional Cedar Clinic.','ultrasound-report.pdf')
        self.foreign=self.source(self.bob,self.bob_workspace,'FOREIGN-PATIENT-RECORD','foreign.pdf')

    def source(self,user,workspace,text,name):
        version,_=services.ingest(user,workspace.pk,SimpleUploadedFile(name,pdf(text)))
        pages=worker.extract(version)
        TextExtraction.objects.create(workspace=workspace,source_version=version,pages=pages,extractor_version='fixture-pypdf',text_sha256=assistant.digest(pages))
        return version

    def sign_in(self,user,client=None):
        client=client or self.client
        client.force_login(user,backend='identity.backends.OIDCSessionBackend')
        session=client.session
        session['oidc_expires_at']=int(time.time())+300
        session.save()

    def create(self,kind='search',parameters=None):
        return assistant.create_task(self.alice,self.workspace.pk,kind,parameters or {'query':'Find a blood count report'})

    def claim(self,task):
        task.state='processing'
        task.lease_token=uuid.uuid4()
        task.lease_expires_at=timezone.now()+timedelta(seconds=180)
        task.save()
        return task.lease_token

    def citation(self,task,version=None,term=None):
        source=task.sources.get(source_version=version or self.alpha)
        chunk=next(c for c in source.chunks if c['locator']['kind']=='source_text')
        return source,{'chunk_id':chunk['id'],'quote':chunk['text'][:200]}

    def search_payload(self,task):
        source,citation=self.citation(task)
        return {'matches':[{'source_id':source.source_label,'reason':'This is a CBC report.','citations':[citation]}],'abstained':False}

    def generate(self,task,payload,side_effect=None,finish_reason='stop'):
        token=self.claim(task)
        response={'choices':[{'finish_reason':finish_reason,'message':{'content':json.dumps(payload)}}], 'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}
        with patch('records.assistant_worker.configuration',return_value={'model':'swiss-ai/Apertus-v1.5-8B','base':'https://example.invalid/v1','key':'test-api-key-not-real'}),patch('records.assistant_worker.available_models'),patch('records.assistant_worker.request_json',side_effect=side_effect,return_value=response):
            state=assistant_worker.process_one(task.pk,token)
        task.refresh_from_db()
        return state

    def test_search_only_snapshots_authorized_current_sources(self):
        task=self.create()
        context,_=assistant.task_context(task)
        rendered=json.dumps(context)
        self.assertNotIn('FOREIGN-PATIENT-RECORD',rendered)
        self.assertNotIn(str(self.foreign.pk),rendered)
        self.assertEqual(task.coverage['included_records'],2)
        self.assertEqual(self.generate(task,self.search_payload(task)),'completed')
        match=task.result['matches'][0]
        self.assertEqual(match['source_version_id'],str(self.alpha.pk))
        self.assertEqual(match['citations'][0]['source_sha256'],self.alpha.sha256)
        self.assertEqual(task.model_name,'swiss-ai/Apertus-v1.5-8B')
        self.assertNotIn('test-api-key-not-real',json.dumps(task.configuration))
        self.assertEqual(task.usage['total_tokens'],150)

    def test_pending_api_returns_saved_task_without_invented_result(self):
        task=self.create()
        token=self.claim(task)
        with patch('records.assistant_worker.configuration',side_effect=assistant_worker.TrialError('missing')),patch('records.assistant_worker.request_json') as request:
            self.assertEqual(assistant_worker.process_one(task.pk,token),'waiting_model')
            request.assert_not_called()
        task.refresh_from_db()
        self.assertIsNone(task.result)
        response=self.client.get(self.base+f'assistant/tasks/{task.pk}/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['state'],'waiting_model')

    def test_unknown_ids_and_wrong_match_citations_rejected(self):
        task=self.create()
        _,sources=assistant.task_context(task)
        payload=self.search_payload(task)
        payload['matches'][0]['source_id']='s999'
        with self.assertRaises(ValueError): assistant.validate_response(task,payload,sources)
        payload=self.search_payload(task)
        other,_=self.citation(task,self.beta)
        payload['matches'][0]['source_id']=other.source_label
        with self.assertRaises(ValueError): assistant.validate_response(task,payload,sources)

    def test_forged_quote_or_tool_fields_fail(self):
        task=self.create()
        payload=self.search_payload(task)
        payload['matches'][0]['citations'][0]['quote']='Invented finding'
        self.assertEqual(self.generate(task,payload),'failed')
        self.assertEqual(task.safe_error_code,'invalid_model_output')
        self.assertIsNone(task.result)
        _,sources=assistant.task_context(task)
        payload=self.search_payload(task)
        payload['tool_calls']=[]
        with self.assertRaises(ValueError): assistant.validate_response(task,payload,sources)

    def test_packet_only_selected_sources_and_frozen_metadata(self):
        services.review(self.alice,self.workspace.pk,self.alpha.record_id,{**VALUES,'facility_name':'Old confirmed label'},0,self.alpha.pk)
        packet=services.create_packet(self.alice,self.workspace.pk,'Follow up',[str(self.alpha.pk)])
        services.review(self.alice,self.workspace.pk,self.alpha.record_id,{**VALUES,'facility_name':'New confirmed label'},1,self.alpha.pk)
        task=self.create('packet_overview',{'packet_id':str(packet.pk)})
        context,_=assistant.task_context(task)
        self.assertEqual(task.sources.count(),1)
        self.assertIn('Old confirmed label',json.dumps(context))
        self.assertNotIn('New confirmed label',json.dumps(context))
        self.assertNotIn('Ultrasound report',json.dumps(context))
        _,citation=self.citation(task)
        payload={'items':[{'text':'The selected report mentions CBC.','citations':[citation]}],'abstained':False}
        self.assertEqual(self.generate(task,payload),'completed')
        self.assertFalse(task.result['modifies_packet'])
        self.assertEqual(packet.revisions.get().items.count(),1)

    def test_unselected_source_cannot_be_cited_in_overview(self):
        packet=services.create_packet(self.alice,self.workspace.pk,'Follow up',[str(self.alpha.pk)])
        task=self.create('packet_overview',{'packet_id':str(packet.pk)})
        payload={'items':[{'text':'Unselected ultrasound','citations':[{'chunk_id':'s999-c0','quote':'Ultrasound'}]}],'abstained':False}
        self.assertEqual(self.generate(task,payload),'failed')
        self.assertEqual(task.safe_error_code,'invalid_model_output')

    def test_term_returns_reviewed_definition_and_reference(self):
        task=self.create('explain_term',{'source_version_id':str(self.alpha.pk),'term':'CBC'})
        _,citation=self.citation(task)
        self.assertEqual(self.generate(task,{'definition_id':'cbc','citations':[citation],'abstained':False}),'completed')
        self.assertEqual(task.result['reference']['url'],'https://medlineplus.gov/lab-tests/complete-blood-count-cbc/')
        self.assertIn('blood tests',task.result['explanation'])
        self.assertNotIn('patient has',task.result['explanation'])

    def test_term_must_be_present_and_in_reviewed_glossary(self):
        for term in ['Invented treatment','MRI']:
            with self.assertRaises(ValueError):
                self.create('explain_term',{'source_version_id':str(self.alpha.pk),'term':term})
        self.assertEqual(AssistantTask.objects.count(),0)

    def test_term_cannot_generate_advice_or_unapproved_definition(self):
        task=self.create('explain_term',{'source_version_id':str(self.alpha.pk),'term':'CBC'})
        _,citation=self.citation(task)
        self.assertEqual(self.generate(task,{'definition_id':'cbc','citations':[citation],'abstained':False,'explanation':'Take medication'}),'failed')
        _,sources=assistant.task_context(task)
        with self.assertRaises(ValueError):
            assistant.validate_response(task,{'definition_id':'mri','citations':[citation],'abstained':False},sources)

    def test_abstention_is_explicit_without_claims(self):
        task=self.create()
        self.assertEqual(self.generate(task,{'matches':[],'abstained':True}),'completed')
        self.assertEqual(task.result,{'matches':[],'abstained':True})

    def test_other_patient_and_anonymous_are_denied_all_assistant_routes(self):
        task=self.create()
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+'assistant/tasks/').status_code,404)
        self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,404)
        self.assertEqual(self.client.post(self.base+f'assistant/tasks/{task.pk}/cancel/').status_code,404)
        self.assertEqual(self.client.post(self.base+'assistant/tasks/',data=json.dumps({'kind':'search','parameters':{'query':'CBC'}}),content_type='application/json').status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,401)

    def test_foreign_source_or_packet_is_unavailable(self):
        with self.assertRaises(Exception) as context:
            self.create('explain_term',{'source_version_id':str(self.foreign.pk),'term':'CBC'})
        self.assertEqual(type(context.exception).__name__,'Http404')
        packet=services.create_packet(self.bob,self.bob_workspace.pk,'Foreign',[str(self.foreign.pk)])
        response=self.client.post(self.base+'assistant/tasks/',data=json.dumps({'kind':'packet_overview','parameters':{'packet_id':str(packet.pk)}}),content_type='application/json')
        self.assertEqual(response.status_code,404)

    def test_revocation_before_generation_prevents_provider_use(self):
        task=self.create()
        token=self.claim(task)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
        with patch('records.assistant_worker.request_json') as request:
            self.assertEqual(assistant_worker.process_one(task.pk,token),'failed')
            request.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.safe_error_code,'authority_unavailable')
        self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,404)

    def test_revocation_during_generation_blocks_publication(self):
        task=self.create()
        payload=self.search_payload(task)
        def provider(*args):
            AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}]}
        self.assertEqual(self.generate(task,payload,side_effect=provider),'failed')
        self.assertIsNone(task.result)
        self.assertEqual(task.safe_error_code,'authority_unavailable')

    def test_prepare_permission_required_for_packet_overview_and_result(self):
        packet=services.create_packet(self.alice,self.workspace.pk,'Follow up',[str(self.alpha.pk)])
        task=self.create('packet_overview',{'packet_id':str(packet.pk)})
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='prepare_packet').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,404)
        self.assertEqual(self.client.get(self.base+'assistant/tasks/').json()['tasks'],[])
        with self.assertRaises(Exception) as context: self.create('packet_overview',{'packet_id':str(packet.pk)})
        self.assertEqual(type(context.exception).__name__,'Http404')

    def test_active_limit_and_cancellation_preserve_history(self):
        task=self.create()
        with self.assertRaises(services.Conflict): self.create()
        assistant.cancel_task(self.alice,self.workspace.pk,task.pk)
        task.refresh_from_db()
        self.assertEqual(task.state,'failed')
        self.assertEqual(task.safe_error_code,'cancelled_by_user')
        replacement=self.create()
        self.assertNotEqual(task.pk,replacement.pk)
        self.assertEqual(task.sources.count(),2)

    def test_old_lease_after_cancel_cannot_publish(self):
        task=self.create()
        token=self.claim(task)
        assistant.cancel_task(self.alice,self.workspace.pk,task.pk)
        self.assertEqual(assistant_worker.process_one(task.pk,token),'failed')
        task.refresh_from_db()
        self.assertEqual(task.safe_error_code,'cancelled_by_user')
        self.assertIsNone(task.result)

    def test_source_integrity_prevents_generation(self):
        task=self.create()
        original=storage.object_path(self.alpha.private_object_key)
        original.chmod(0o600)
        original.write_bytes(b'corrupt')
        token=self.claim(task)
        with patch('records.assistant_worker.request_json') as request:
            self.assertEqual(assistant_worker.process_one(task.pk,token),'failed')
            request.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.safe_error_code,'source_integrity_or_storage')

    def test_snapshot_integrity_and_context_bounds(self):
        with patch('records.assistant.CONTEXT_LIMIT',100): task=self.create()
        self.assertLessEqual(sum(len(c['text']) for source in task.sources.all() for c in source.chunks),100)
        self.assertGreater(task.coverage['truncated_sources'],0)
        with patch('records.assistant.digest',return_value='0'*64):
            with self.assertRaises(ValueError): assistant.task_context(task)

    def test_provider_failure_and_truncation_no_retries_or_partial_result(self):
        task=self.create()
        self.assertEqual(self.generate(task,self.search_payload(task),side_effect=assistant_worker.TrialError('safe')),'failed')
        self.assertEqual(task.safe_error_code,'model_access_failed')
        replacement=self.create()
        self.assertEqual(self.generate(replacement,self.search_payload(replacement),finish_reason='length'),'failed')
        self.assertIsNone(replacement.result)

    def test_untrusted_provider_cannot_store_api_key(self):
        task=self.create()
        payload=self.search_payload(task)
        payload['matches'][0]['reason']='test-api-key-not-real'
        self.assertEqual(self.generate(task,payload),'failed')
        self.assertIsNone(task.result)

    def test_csrf_and_closed_inputs(self):
        client=Client(enforce_csrf_checks=True)
        self.sign_in(self.alice,client)
        payload={'kind':'search','parameters':{'query':'CBC'}}
        self.assertEqual(client.post(self.base+'assistant/tasks/',data=json.dumps(payload),content_type='application/json').status_code,403)
        payload['parameters']['base_url']='https://untrusted.example'
        self.assertEqual(self.client.post(self.base+'assistant/tasks/',data=json.dumps(payload),content_type='application/json').status_code,400)

    def test_workspace_controls_and_restricted_script_policy(self):
        response=self.client.get(f'/workspaces/{self.workspace.pk}/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'upload-form')
        self.assertContains(response,'Ask Apertus')
        self.assertContains(response,'Explain with Apertus')
        self.assertIn("script-src 'self'",response['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline',response['Content-Security-Policy'])
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/').status_code,404)

    def test_status_is_scoped_and_never_exposes_credentials(self):
        with patch('intelligence.trial.configuration',return_value={'model':'local-registered-model','key':'test-secret','identity':{'modalities':['text'],'community_derivative':True}}):
            response=self.client.get(self.base+'assistant/status/')
        self.assertTrue(response.json()['configured'])
        self.assertNotIn('test-secret',response.content.decode())
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+'assistant/status/').status_code,404)

    def test_image_only_overview_explains_missing_text_without_model_generation(self):
        from io import BytesIO
        from PIL import Image
        original=BytesIO(); Image.new('RGB',(8,8),'white').save(original,format='PNG')
        version,_=services.ingest(self.alice,self.workspace.pk,SimpleUploadedFile('synthetic-mri.png',original.getvalue()),content_kind='medical_image')
        packet=services.create_packet(self.alice,self.workspace.pk,'Images',[str(version.pk)])
        with patch('records.assistant_worker.configuration') as config,patch('records.assistant_worker.request_json') as request:
            task=self.create('packet_overview',{'packet_id':str(packet.pk)})
            self.assertEqual(task.state,'completed')
            config.assert_not_called(); request.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.result['limitation_code'],'no_readable_report_text')
        self.assertFalse(task.configuration['model_generation_performed'])
        self.assertEqual(task.model_name,'')
        self.assertTrue(task.result['abstained'])
        self.assertFalse(task.result['modifies_packet'])

    def test_local_assistant_grammar_cannot_bypass_citation_validation(self):
        task=self.create()
        payload=self.search_payload(task); payload['matches'][0]['citations'][0]['quote']='invented evidence'
        token=self.claim(task)
        config={'model':assistant_worker.LOCAL_TEXT_MODEL,'base':'http://host.docker.internal:9001/v1','key':'test-local'}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}]}
        with patch('records.assistant_worker.configuration',return_value=config),patch('records.assistant_worker.available_models'),patch('records.assistant_worker.request_json',return_value=response) as request:
            self.assertEqual(assistant_worker.process_one(task.pk,token),'failed')
        format=request.call_args.args[2]['response_format']
        self.assertEqual(format['type'],'json_schema')
        rendered=json.dumps(format)
        self.assertNotIn('FOREIGN-PATIENT-RECORD',rendered)
        task.refresh_from_db(); self.assertIsNone(task.result)
        self.assertEqual(task.configuration['output_format']['response_format'],format)

    def test_term_input_error_explains_the_missing_context(self):
        response=self.client.post(self.base+'assistant/tasks/',data=json.dumps({'kind':'explain_term','parameters':{'source_version_id':str(self.alpha.pk),'term':'MRI'}}),content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertIn('term must occur',response.json()['error'])
        self.assertFalse(AssistantTask.objects.exists())

    @skipUnless(connection.vendor=='postgresql','PostgreSQL assistant guards')
    def test_database_protects_snapshots_parameters_and_terminal_results(self):
        task=self.create()
        source=task.sources.get(source_version=self.alpha)
        with self.assertRaises(IntegrityError),transaction.atomic(): AssistantSource.objects.filter(pk=source.pk).update(chunks=[])
        with self.assertRaises(IntegrityError),transaction.atomic(): AssistantTask.objects.filter(pk=task.pk).update(parameters={})
        with self.assertRaises(IntegrityError),transaction.atomic(): AssistantTask.objects.filter(pk=task.pk).update(state='completed',result={})
        self.generate(task,self.search_payload(task))
        with self.assertRaises(IntegrityError),transaction.atomic(): AssistantTask.objects.filter(pk=task.pk).update(result={})

    @skipUnless(connection.vendor=='postgresql','PostgreSQL source scope')
    def test_database_rejects_unselected_packet_or_cross_workspace_source(self):
        packet=services.create_packet(self.alice,self.workspace.pk,'Follow up',[str(self.alpha.pk)])
        task=self.create('packet_overview',{'packet_id':str(packet.pk)})
        with self.assertRaises(IntegrityError),transaction.atomic():
            AssistantSource.objects.create(workspace=self.workspace,task=task,source_version=self.beta,source_label='s999',metadata_revision=0,chunks=[],snapshot_sha256='0'*64)
        with self.assertRaises(IntegrityError),transaction.atomic():
            AssistantSource.objects.create(workspace=self.workspace,task=task,source_version=self.foreign,source_label='s998',metadata_revision=0,chunks=[],snapshot_sha256='0'*64)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL runtime permissions')
    def test_generation_uses_restricted_role_without_locking_immutable_sources(self):
        from identity.db_roles import configure_runtime_permissions
        configure_runtime_permissions(connection)
        task=self.create()
        payload=self.search_payload(task)
        try:
            with connection.cursor() as cursor: cursor.execute('SET ROLE continuity_app')
            self.assertEqual(self.generate(task,payload),'completed')
            self.assertEqual(self.client.get(self.base+f'assistant/tasks/{task.pk}/').status_code,200)
        finally:
            with connection.cursor() as cursor: cursor.execute('RESET ROLE')
