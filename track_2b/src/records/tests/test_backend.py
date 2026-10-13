from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import uuid
from unittest import skipUnless
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from identity.models import AccessCapability, PatientWorkspace
from identity.services import resolve_verified_identity
from records import services, storage, worker
from records.metadata import UNKNOWN_DATE, validate_model_output, validate_values
from records.models import (DerivedArtifact, GenerationRun, IngestionJob, MetadataAssertion,
                            PacketSourceItem, SourceRecord, SourceVersion, TextExtraction)
import pypdf
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def pdf(text='Laboratory Report | Document date: September 2026 | Facility: Fictional Cedar Clinic'):
    writer=pypdf.PdfWriter()
    page=writer.add_blank_page(width=600,height=800)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject()
    safe=text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    stream.set_data(f'BT /F1 12 Tf 20 760 Td ({safe}) Tj ET'.encode())
    page[NameObject('/Contents')]=writer._add_object(stream)
    output=BytesIO()
    writer.write(output)
    return output.getvalue()


VALUES={'document_type':'lab_report','document_date':{'precision':'month','year':2026,'month':9,'day':None},'facility_name':'Fictional Cedar Clinic'}


class BackendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice=resolve_verified_identity('https://test.example/issuer','records-alice','Alice')
        cls.bob=resolve_verified_identity('https://test.example/issuer','records-bob','Bob')
        cls.workspace=PatientWorkspace.objects.get(subject_patient__person=cls.alice.person)
        cls.bob_workspace=PatientWorkspace.objects.get(subject_patient__person=cls.bob.person)

    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.setting=override_settings(PRIVATE_STORAGE_ROOT=Path(self.directory.name))
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        self.sign_in(self.alice)
        self.base=f'/api/workspaces/{self.workspace.pk}/'

    def sign_in(self,user,client=None):
        client=client or self.client
        client.force_login(user,backend='identity.backends.OIDCSessionBackend')
        session=client.session
        session['oidc_expires_at']=int(time.time())+300
        session.save()

    def upload(self,text=None,record=None):
        data=pdf() if text is None else pdf(text)
        route=self.base+'records/' if record is None else self.base+f'records/{record.pk}/versions/'
        response=self.client.post(route,{'file':SimpleUploadedFile('synthetic.pdf',data,content_type='application/pdf')})
        self.assertEqual(response.status_code,201,response.content)
        return SourceVersion.objects.get(pk=response.json()['version']['id'])

    def confirm(self,version,values=None,revision=0):
        return self.client.post(self.base+f'records/{version.record_id}/review/',data=json.dumps({
            'values':values or VALUES,'expected_revision':revision,'source_version_id':str(version.pk)}),content_type='application/json')

    def claim(self,version):
        job=version.jobs.latest('attempt_number')
        job.state='processing'
        job.lease_token=uuid.uuid4()
        job.lease_expires_at=timezone.now()+timedelta(seconds=180)
        job.save()
        return job

    def test_upload_download_duplicate_and_private_paths(self):
        version=self.upload()
        response=self.client.get(self.base+f'versions/{version.pk}/original/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(b''.join(response.streaming_content),pdf())
        self.assertIn('attachment',response['Content-Disposition'])
        duplicate=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('duplicate.pdf',pdf())})
        self.assertEqual(duplicate.status_code,200)
        self.assertEqual(duplicate.json()['version']['id'],str(version.pk))
        self.assertEqual(SourceRecord.objects.count(),1)
        self.assertEqual(IngestionJob.objects.count(),1)
        listing=self.client.get(self.base+'records/').content.decode()
        self.assertNotIn(version.private_object_key,listing)
        self.assertNotIn('private_object_key',listing)

    def location_review(self,version,url,revision=0,values=None,include=True):
        payload={'source_version_id':str(version.pk),'expected_revision':revision,'values':values or VALUES}
        if include:
            payload['facility_maps_url']=url
        return self.client.post(self.base+f'records/{version.record_id}/review/',data=json.dumps(payload),content_type='application/json')

    def test_facility_pin_review_history_and_frozen_packet(self):
        version=self.upload()
        first='https://maps.app.goo.gl/CedarBranch123?g_st=ic'
        second='https://www.google.com/maps/search/?api=1&query=Other+Clinic'
        response=self.location_review(version,first)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['facility_maps_url'],first)
        assertion=response.json()['assertion_ids']['facility_name']
        packet=services.create_packet(self.alice,self.workspace.pk,'Pinned facility',[str(version.pk)])
        updated={**VALUES,'facility_name':'Other Clinic'}
        self.assertEqual(self.location_review(version,second,1,updated).status_code,200)
        frozen=self.client.get(self.base+f'packets/{packet.pk}/').json()['items'][0]
        self.assertEqual(frozen['facility_maps_url'],first)
        self.assertEqual(str(frozen['assertion_ids']['facility_name']),assertion)
        record=self.client.get(self.base+f'records/{version.record_id}/').json()
        self.assertEqual(record['metadata']['facility_maps_url'],second)
        self.assertTrue(any(item['id']==assertion and item['facility_maps_url']==first for item in record['metadata_history']))
        self.assertEqual(self.client.get(self.base+'records/').json()['records'][0]['metadata']['facility_maps_url'],second)

    def test_independent_uploads_keep_successes_when_another_file_fails(self):
        first=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('first.pdf',pdf('Synthetic first report'))})
        invalid=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('invalid.png',b'not an image')})
        third=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('third.pdf',pdf('Synthetic third report'))})
        self.assertEqual([first.status_code,invalid.status_code,third.status_code],[201,400,201])
        self.assertEqual(SourceRecord.objects.count(),2)
        self.assertEqual(IngestionJob.objects.count(),2)
        duplicate=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('first.pdf',pdf('Synthetic first report'))})
        self.assertEqual(duplicate.status_code,200)
        self.assertEqual(SourceRecord.objects.count(),2)
        page=self.client.get(f'/workspaces/{self.workspace.pk}/').content.decode()
        self.assertIn('multiple required',page)
        self.assertIn('Retry failed files',page)

    def test_facility_pin_rejects_untrusted_urls_and_missing_name_atomically(self):
        version=self.upload()
        invalid=['javascript:alert(1)','http://www.google.com/maps/place/Clinic','https://google.com.evil.invalid/maps/Clinic',
            'https://maps.app.goo.gl@evil.invalid/abc','https://user:password@www.google.com/maps/place/Clinic',
            'https://www.google.com:8443/maps/place/Clinic','https://www.google.com/search?q=Clinic',
            'https://www.google.com/maps/%0aClinic','https://maps.app.goo.gl/abc\\evil','https://evil.invalid/pin',False]
        for url in invalid:
            with self.subTest(url=url):
                self.assertEqual(self.location_review(version,url).status_code,400)
        self.assertEqual(self.location_review(version,'https://maps.app.goo.gl/Cedar123',values={**VALUES,'facility_name':None}).status_code,400)
        self.assertFalse(version.assertions.exists())
        self.assertEqual(version.metadata_head.revision,0)

    def test_facility_pin_backward_compatibility_and_explicit_removal(self):
        version=self.upload()
        pin='https://goo.gl/maps/Cedar123'
        self.assertEqual(self.location_review(version,pin).status_code,200)
        retained=self.location_review(version,None,1,include=False)
        self.assertEqual(retained.json()['facility_maps_url'],pin)
        removed=self.location_review(version,None,2)
        self.assertIsNone(removed.json()['facility_maps_url'])
        self.assertEqual(self.location_review(version,pin,3).status_code,200)
        changed=self.location_review(version,None,4,{**VALUES,'facility_name':'Different facility'},include=False)
        self.assertIsNone(changed.json()['facility_maps_url'])

    def test_search_selection_saves_full_location_and_preserves_packet_snapshot(self):
        from records.facilities import selection_token
        from records.facility_search import normalize_results
        version=self.upload()
        location=normalize_results([{'name':VALUES['facility_name'],'display_name':'Fictional Cedar Clinic, Example Town','lat':'-1.2','lon':'36.8','type':'clinic','category':'amenity','osm_type':'node','osm_id':123}])[0]
        token=selection_token(location,self.alice,self.workspace.pk)
        payload={'values':VALUES,'source_version_id':str(version.pk),'expected_revision':0,'facility_selection':token}
        response=self.client.post(self.base+f'records/{version.record_id}/review/',data=json.dumps(payload),content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['facility_location'],location)
        packet=services.create_packet(self.alice,self.workspace.pk,'Chosen hospital',[str(version.pk)])
        self.location_review(version,None,1)
        self.assertEqual(self.client.get(self.base+f'packets/{packet.pk}/').json()['items'][0]['facility_location'],location)
        payload['expected_revision']=2; payload['values']={**VALUES,'facility_name':'Another hospital'}
        self.assertEqual(self.client.post(self.base+f'records/{version.record_id}/review/',data=json.dumps(payload),content_type='application/json').status_code,400)

    def test_facility_pin_keeps_live_read_and_review_authority(self):
        version=self.upload()
        self.assertEqual(self.location_review(version,'https://maps.app.goo.gl/Cedar123').status_code,200)
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+f'records/{version.record_id}/').status_code,404)
        self.assertEqual(self.location_review(version,'https://maps.app.goo.gl/Other123',1).status_code,404)
        self.sign_in(self.alice)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+'records/').status_code,404)
        self.assertEqual(self.location_review(version,None,1).status_code,404)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL history guard')
    def test_facility_pin_database_scope_and_history_guards(self):
        version=self.upload()
        self.location_review(version,'https://maps.app.goo.gl/Cedar123')
        assertion=version.assertions.get(field_name='facility_name')
        with self.assertRaises(IntegrityError),transaction.atomic():
            MetadataAssertion.objects.filter(pk=assertion.pk).update(facility_maps_url='https://maps.app.goo.gl/Other123')
        for field,url in [('document_type','https://maps.app.goo.gl/Cedar123'),('facility_name','https://evil.invalid/pin')]:
            with self.subTest(field=field),self.assertRaises(IntegrityError),transaction.atomic():
                MetadataAssertion.objects.create(workspace=self.workspace,source_version=version,field_name=field,value_type='text',
                    value_text='Clinic',origin='patient',review_state='confirmed',asserted_by=self.alice,facility_maps_url=url)

    def test_two_patient_isolation_on_all_paths(self):
        version=self.upload()
        self.sign_in(self.bob)
        for route in [f'records/{version.record_id}/',f'versions/{version.pk}/original/','records/','packets/']:
            self.assertEqual(self.client.get(self.base+route).status_code,404)
        self.assertEqual(self.client.post(self.base+'records/',{'file':SimpleUploadedFile('x.pdf',pdf())}).status_code,404)
        self.assertEqual(self.confirm(version).status_code,404)
        self.assertEqual(self.client.get(f'/api/workspaces/{self.bob_workspace.pk}/records/{version.record_id}/').status_code,404)

    def test_cross_workspace_duplicate_is_not_a_global_dedup_oracle(self):
        version=self.upload()
        other,_=services.ingest(self.bob,self.bob_workspace.pk,SimpleUploadedFile('same.pdf',pdf()))
        self.assertNotEqual(other.pk,version.pk)
        self.assertNotEqual(other.private_object_key,version.private_object_key)

    def test_explicit_write_permission_and_revocation(self):
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='upload_source').update(revoked_at=timezone.now())
        self.assertEqual(self.client.post(self.base+'records/',{'file':SimpleUploadedFile('x.pdf',pdf())}).status_code,404)
        self.assertEqual(self.client.get(self.base+'records/').status_code,200)

    def test_expired_permission_and_session_deny(self):
        version=self.upload()
        cap=AccessCapability.objects.get(membership__user=self.alice,rule__capability_key='read_workspace_records')
        cap.valid_until=cap.valid_from+timedelta(seconds=5)
        cap.save(update_fields=['valid_until'])
        with patch('identity.authorization.timezone.now',return_value=cap.valid_until+timedelta(seconds=1)):
            self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/original/').status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(self.base+'records/').status_code,401)

    def test_invalid_empty_and_oversized_uploads(self):
        for name,data in [('bad.pdf',b'<html>fake PDF</html>'),('bad.html',pdf()),('empty.pdf',b''),('large.pdf',b'%PDF-'+b'x'*(storage.LIMIT+1))]:
            response=self.client.post(self.base+'records/',{'file':SimpleUploadedFile(name,data)})
            self.assertEqual(response.status_code,400)
        self.assertFalse(SourceVersion.objects.exists())

    def test_new_version_preserves_old_bytes_and_lineage(self):
        first=self.upload()
        second=self.upload('Referral Letter | Document date: 2026-09-20',first.record)
        self.assertEqual(second.version_number,2)
        self.assertEqual(second.supersedes_id,first.pk)
        self.assertEqual(storage.read_original(first),pdf())
        self.assertEqual(first.record.versions.count(),2)

    def test_storage_integrity_failure_blocks_download(self):
        version=self.upload()
        path=storage.object_path(version.private_object_key)
        path.chmod(0o600)
        path.write_bytes(b'tampered')
        self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/original/').status_code,503)

    def test_failed_storage_write_leaves_no_record_or_job(self):
        with patch('records.services.write_original',side_effect=storage.StorageError('unavailable')):
            response=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('x.pdf',pdf())})
        self.assertEqual(response.status_code,503)
        self.assertFalse(SourceRecord.objects.exists())
        self.assertFalse(IngestionJob.objects.exists())

    def test_review_history_partial_date_and_stale_write(self):
        version=self.upload()
        self.assertEqual(self.confirm(version).status_code,200)
        values={**VALUES,'facility_name':'Patient corrected facility'}
        self.assertEqual(self.confirm(version,values,0).status_code,409)
        self.assertEqual(self.confirm(version,values,1).status_code,200)
        self.assertEqual(version.assertions.count(),6)
        self.assertEqual(version.assertions.filter(supersedes__isnull=False).count(),3)
        detail=self.client.get(self.base+f'records/{version.record_id}/').json()
        self.assertEqual(detail['metadata']['values']['document_date'],VALUES['document_date'])
        self.assertEqual(detail['metadata']['revision'],2)
        self.assertEqual(len(detail['metadata_history']),6)
        self.assertEqual(storage.read_original(version),pdf())

    def test_review_cannot_apply_to_old_version_after_replacement(self):
        old=self.upload()
        self.upload('Replacement source text',old.record)
        self.assertEqual(self.confirm(old).status_code,409)

    def test_bad_calendar_and_partial_date_shapes_rejected(self):
        for parts in [{'precision':'day','year':2023,'month':2,'day':29},
                      {'precision':'month','year':2026,'month':0,'day':None},
                      {'precision':'month','year':2026,'month':9,'day':1},
                      {'precision':'unknown','year':2026,'month':None,'day':None}]:
            with self.assertRaises(ValueError):
                validate_values({**VALUES,'document_date':parts})

    def test_packet_exact_selection_and_frozen_metadata(self):
        version=self.upload()
        unselected=self.upload('Unselected consultation note')
        self.assertEqual(self.confirm(version).status_code,200)
        response=self.client.post(self.base+'packets/',data=json.dumps({'purpose':'Demo consultation','source_version_ids':[str(version.pk)]}),content_type='application/json')
        self.assertEqual(response.status_code,201,response.content)
        packet=response.json()
        self.assertEqual([item['source_version']['id'] for item in packet['items']],[str(version.pk)])
        self.assertNotIn(str(unselected.pk),response.content.decode())
        self.confirm(version,{**VALUES,'facility_name':'Later correction'},1)
        frozen=self.client.get(self.base+f"packets/{packet['id']}/").json()
        self.assertEqual(frozen['items'][0]['metadata']['facility_name'],VALUES['facility_name'])
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+f"packets/{packet['id']}/").status_code,404)

    def test_packet_rejects_foreign_or_duplicate_selection(self):
        foreign,_=services.ingest(self.bob,self.bob_workspace.pk,SimpleUploadedFile('x.pdf',pdf()))
        self.assertEqual(self.client.post(self.base+'packets/',data=json.dumps({'purpose':'Demo','source_version_ids':[str(foreign.pk)]}),content_type='application/json').status_code,404)
        self.assertEqual(self.client.post(self.base+'packets/',data=json.dumps({'purpose':'Demo','source_version_ids':[str(foreign.pk)]*2}),content_type='application/json').status_code,400)

    def test_search_uses_only_authorized_confirmed_metadata(self):
        version=self.upload()
        self.confirm(version)
        self.assertEqual(len(self.client.get(self.base+'records/?q=Cedar').json()['records']),1)
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+'records/?q=Cedar').status_code,404)

    def test_api_writes_require_csrf(self):
        client=Client(enforce_csrf_checks=True)
        self.sign_in(self.alice,client)
        self.assertEqual(client.post(self.base+'records/',{'file':SimpleUploadedFile('x.pdf',pdf())}).status_code,403)
        client.get(self.base+'records/')
        token=client.cookies['csrftoken'].value
        self.assertEqual(client.post(self.base+'records/',{'file':SimpleUploadedFile('x.pdf',pdf())},HTTP_X_CSRFTOKEN=token).status_code,201)

    def test_no_api_key_preserves_extraction_and_waits_without_fabricating_metadata(self):
        version=self.upload()
        job=self.claim(version)
        with patch('records.worker.configuration',side_effect=worker.TrialError('missing')),patch('records.worker.request_json') as request:
            self.assertEqual(worker.process_one(job.pk,job.lease_token),'waiting_model')
        request.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state,'waiting_model')
        self.assertTrue(TextExtraction.objects.filter(source_version=version).exists())
        self.assertFalse(DerivedArtifact.objects.exists())
        self.assertEqual(storage.read_original(version),pdf())

    @skipUnless(connection.vendor=='postgresql','Restricted PostgreSQL runtime role')
    def test_worker_runs_with_runtime_role_without_locking_immutable_sources(self):
        from identity.db_roles import configure_runtime_permissions
        version=self.upload()
        job=self.claim(version)
        configure_runtime_permissions(connection)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET ROLE continuity_app')
            with patch('records.worker.configuration',side_effect=worker.TrialError('missing')):
                self.assertEqual(worker.process_one(job.pk,job.lease_token),'waiting_model')
        finally:
            with connection.cursor() as cursor:
                cursor.execute('RESET ROLE')

    def test_images_need_ocr_and_original_remains(self):
        from PIL import Image
        output=BytesIO()
        Image.new('RGB',(8,8),'white').save(output,format='PNG')
        data=output.getvalue()
        response=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('scan.png',data)})
        self.assertEqual(response.status_code,201)
        version=SourceVersion.objects.get(pk=response.json()['version']['id'])
        job=self.claim(version)
        self.assertEqual(worker.process_one(job.pk,job.lease_token),'needs_ocr')
        self.assertEqual(storage.read_original(version),data)

    def test_mocked_model_proposals_do_not_overwrite_patient_review(self):
        version=self.upload()
        self.confirm(version)
        pages=worker.extract(version)
        quote=pages[0]['text'].strip()
        payload={**VALUES,'evidence':{field:{'page':1,'quote':quote} for field in VALUES}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}],'usage':{'total_tokens':111}}
        job=self.claim(version)
        with patch('records.worker.configuration',return_value={'model':'swiss-ai/Apertus-v1.5-8B','base':'https://example.invalid/v1','key':'test-only'}),patch('records.worker.available_models'),patch('records.worker.request_json',return_value=response):
            self.assertEqual(worker.process_one(job.pk,job.lease_token),'review_ready')
        self.assertEqual(version.metadata_head.revision,1)
        self.assertEqual(version.assertions.filter(origin='ai').count(),3)
        self.assertEqual(DerivedArtifact.objects.count(),1)
        self.assertEqual(GenerationRun.objects.get().usage,{'total_tokens':111})

    def test_bad_model_output_and_provider_failure_preserve_original_and_fail(self):
        for response in [{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},worker.TrialError('HTTP 429')]:
            version=self.upload(str(uuid.uuid4()))
            job=self.claim(version)
            with patch('records.worker.configuration',return_value={'model':'swiss-ai/Apertus-v1.5-8B','base':'https://example.invalid/v1','key':'test'}),patch('records.worker.available_models'),patch('records.worker.request_json',side_effect=[response]):
                self.assertEqual(worker.process_one(job.pk,job.lease_token),'failed')
            self.assertTrue(storage.read_original(version))
            job.refresh_from_db()
            self.assertEqual(job.state,'failed')
        self.assertFalse(DerivedArtifact.objects.exists())

    def test_local_metadata_grammar_is_recorded_and_does_not_bypass_source_checks(self):
        version=self.upload()
        job=self.claim(version)
        payload={**VALUES,'evidence':{field:{'page':1,'quote':'invented evidence'} for field in VALUES}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}]}
        config={'model':worker.LOCAL_TEXT_MODEL,'base':'http://host.docker.internal:9001/v1','key':'test-only'}
        with patch('records.worker.configuration',return_value=config),patch('records.worker.available_models'),patch('records.worker.request_json',return_value=response) as request:
            self.assertEqual(worker.process_one(job.pk,job.lease_token),'failed')
        format=request.call_args.args[2]['response_format']
        self.assertEqual(format['type'],'json_schema')
        self.assertEqual(GenerationRun.objects.get().configuration['parameters']['response_format'],format)
        self.assertFalse(DerivedArtifact.objects.exists())
        self.assertTrue(storage.read_original(version))

    def test_revoked_authority_stops_worker(self):
        version=self.upload()
        job=self.claim(version)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='upload_source').update(revoked_at=timezone.now())
        with patch('records.worker.request_json') as request:
            self.assertEqual(worker.process_one(job.pk,job.lease_token),'failed')
        request.assert_not_called()

    def test_write_capabilities_cannot_bypass_revoked_source_read_access(self):
        version=self.upload()
        job=self.claim(version)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
        self.assertEqual(self.confirm(version).status_code,404)
        self.assertEqual(self.client.post(self.base+'packets/',data=json.dumps({'purpose':'Demo','source_version_ids':[str(version.pk)]}),content_type='application/json').status_code,404)
        self.assertEqual(self.client.post(self.base+'records/',{'file':SimpleUploadedFile('copy.pdf',pdf())}).status_code,404)
        self.assertEqual(self.client.post(self.base+f'jobs/{job.pk}/retry/').status_code,404)
        with patch('records.worker.request_json') as request:
            self.assertEqual(worker.process_one(job.pk,job.lease_token),'failed')
        request.assert_not_called()

    def test_retry_keeps_old_attempt_and_limits_retry_scope(self):
        version=self.upload()
        job=version.jobs.get()
        job.state='failed'
        job.safe_error_code='model_access_failed'
        job.save()
        response=self.client.post(self.base+f'jobs/{job.pk}/retry/')
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json()['attempt_number'],2)
        self.assertEqual(version.jobs.count(),2)
        self.assertEqual(self.client.post(self.base+f'jobs/{job.pk}/retry/').status_code,409)

    def test_forged_page_and_extra_model_authority_fields_rejected(self):
        payload={**VALUES,'evidence':{field:{'page':2,'quote':'forged'} for field in VALUES}}
        with self.assertRaises(ValueError):
            validate_model_output(payload,[{'page':1,'text':'Actual source'}])
        with self.assertRaises(ValueError):
            validate_model_output({**payload,'workspace_id':str(self.bob_workspace.pk)},[])

    @skipUnless(connection.vendor=='postgresql','PostgreSQL constraint backstops')
    def test_database_rejects_cross_workspace_and_immutable_source_changes(self):
        version=self.upload()
        for change in [{'sha256':'a'*64},{'workspace_id':self.bob_workspace.pk},{'original_filename':'changed.pdf'}]:
            with self.assertRaises(IntegrityError),transaction.atomic():
                SourceVersion.objects.filter(pk=version.pk).update(**change)
        with self.assertRaises(IntegrityError),transaction.atomic():
            IngestionJob.objects.create(workspace=self.bob_workspace,source_version=version,requested_by=self.bob,attempt_number=2)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL calendar backstop')
    def test_database_rejects_impossible_assertion_date(self):
        version=self.upload()
        with self.assertRaises(IntegrityError),transaction.atomic():
            MetadataAssertion.objects.create(workspace=self.workspace,source_version=version,field_name='document_date',
                value_type='date_components',value_year=2023,value_month=2,value_day=29,date_precision='day',
                origin='patient',review_state='confirmed',asserted_by=self.alice)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL frozen packet guard')
    def test_database_rejects_new_items_after_packet_approval(self):
        first=self.upload()
        second=self.upload('Second source')
        packet=services.create_packet(self.alice,self.workspace.pk,'Demo',[str(first.pk)])
        revision=packet.revisions.get()
        with self.assertRaises(IntegrityError),transaction.atomic():
            PacketSourceItem.objects.create(workspace=self.workspace,revision=revision,source_version=second)
