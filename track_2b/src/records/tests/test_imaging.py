from datetime import timedelta
from io import BytesIO
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import uuid
from unittest import skipUnless
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, UltrasoundImageStorage, UltrasoundMultiFrameImageStorage
from identity.models import AccessCapability, PatientWorkspace
from identity.services import resolve_verified_identity
from records import services, storage, worker
from records.models import ImageInspection, IngestionJob, SourceVersion, TextExtraction, GenerationRun
from records.metadata import UNKNOWN_DATE


def raster(fmt='PNG', size=(32, 24)):
    output=BytesIO()
    Image.new('RGB',size,'white').save(output,format=fmt)
    return output.getvalue()


def dicom(modality='MR', frames=1):
    """Authored tiny synthetic Part 10 file; no downloaded patient data."""
    ds=Dataset()
    ds.SOPClassUID=MRImageStorage if modality=='MR' else (UltrasoundImageStorage if frames==1 else UltrasoundMultiFrameImageStorage)
    ds.SOPInstanceUID='1.2.826.0.1.3680043.8.498.1001'
    ds.StudyInstanceUID='1.2.826.0.1.3680043.8.498.1002'
    ds.SeriesInstanceUID='1.2.826.0.1.3680043.8.498.1003'
    ds.Modality=modality
    ds.StudyDate='20260901'
    ds.InstitutionName='Fictional Cedar Clinic'
    ds.StudyDescription='Synthetic imaging fixture'
    ds.SeriesDescription='Synthetic series'
    ds.PatientName='Synthetic^Only'
    ds.PatientID='DO-NOT-EXPOSE-HEADER'
    ds.Rows=8
    ds.Columns=8
    ds.NumberOfFrames=frames
    ds.SamplesPerPixel=1
    ds.PhotometricInterpretation='MONOCHROME2'
    ds.BitsAllocated=16
    ds.BitsStored=12
    ds.HighBit=11
    ds.PixelRepresentation=0
    ds.PixelData=b'\0\0'*(64*frames)
    ds.file_meta=FileMetaDataset()
    ds.file_meta.TransferSyntaxUID=ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID=ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID=ds.SOPInstanceUID
    output=BytesIO()
    pydicom.dcmwrite(output,ds,enforce_file_format=True)
    return output.getvalue()


class ImagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice=resolve_verified_identity('https://test.example/issuer','imaging-alice','Alice')
        cls.bob=resolve_verified_identity('https://test.example/issuer','imaging-bob','Bob')
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

    def sign_in(self,user):
        self.client.force_login(user,backend='identity.backends.OIDCSessionBackend')
        session=self.client.session
        session['oidc_expires_at']=int(time.time())+300
        session.save()

    def upload(self,name,data,kind='medical_image'):
        response=self.client.post(self.base+'records/',{'file':SimpleUploadedFile(name,data),'content_kind':kind})
        self.assertEqual(response.status_code,201,response.content)
        return SourceVersion.objects.get(pk=response.json()['version']['id'])

    def process(self,version):
        job=version.jobs.get()
        job.state='processing'
        job.lease_token=uuid.uuid4()
        job.lease_expires_at=timezone.now()+timedelta(seconds=180)
        job.save()
        return worker.process_one(job.pk,job.lease_token)

    def test_medical_raster_preview_manual_review_without_llm(self):
        for fmt,ext in [('PNG','png'),('JPEG','jpg')]:
            data=raster(fmt)
            version=self.upload('ultrasound.'+ext,data)
            with patch('records.worker.configuration',side_effect=AssertionError('Must not call model')):
                self.assertEqual(self.process(version),'manual_review')
            details=self.client.get(self.base+f'versions/{version.pk}/image/').json()
            self.assertEqual(details['details']['format'],fmt)
            self.assertEqual(details['details']['width'],32)
            preview=self.client.get(details['preview_url'])
            self.assertEqual(preview.status_code,200)
            preview_bytes=b''.join(preview.streaming_content)
            self.assertEqual(hashlib.sha256(preview_bytes).hexdigest(),details['preview_sha256'])
            self.assertEqual(preview['X-Comfort-Preview'],'non-diagnostic')
            self.assertEqual(Image.open(BytesIO(preview_bytes)).format,'PNG')
            self.assertEqual(storage.read_original(version),data)
            self.assertEqual(version.metadata_head.revision,0)
        self.assertEqual(TextExtraction.objects.count(),0)
        self.assertEqual(GenerationRun.objects.count(),0)

    def test_mri_and_multiframe_ultrasound_dicom_headers_originals(self):
        for modality,frames in [('MR',1),('US',3)]:
            version=self.upload('study.dcm',dicom(modality,frames),'document')
            self.assertEqual(version.content_kind,'medical_image')
            self.assertEqual(self.process(version),'manual_review')
            response=self.client.get(self.base+f'versions/{version.pk}/image/')
            details=response.json()['details']
            self.assertEqual(details['frames'],frames)
            self.assertEqual(details['header_fields']['Modality']['value'],modality)
            self.assertEqual(details['header_fields']['StudyDate']['tag'],'0008,0020')
            self.assertEqual(details['metadata_status'],'source_header_unverified')
            self.assertEqual(details['pixel_validation'],'not_performed')
            self.assertNotIn('PatientName',response.content.decode())
            self.assertNotIn('DO-NOT-EXPOSE-HEADER',response.content.decode())
            self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/preview/').status_code,409)
            self.assertEqual(storage.read_original(version),dicom(modality,frames))
            self.assertEqual(version.metadata_head.revision,0)

    def test_image_access_is_live_and_scoped_to_source_version(self):
        version=self.upload('mri.png',raster())
        self.process(version)
        self.sign_in(self.bob)
        for route in ['image/','preview/','original/']:
            self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/'+route).status_code,404)
            self.assertEqual(self.client.get(f'/api/workspaces/{self.bob_workspace.pk}/versions/{version.pk}/'+route).status_code,404)
        self.sign_in(self.alice)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/preview/').status_code,404)
        self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/image/').status_code,404)

    def test_invalid_images_fail_without_losing_original(self):
        for name,data in [('bad.png',b'\x89PNG\r\n\x1a\ninvalid'),('bad.dcm',b'\0'*128+b'DICM'+b'invalid')]:
            version=self.upload(name,data)
            self.assertEqual(self.process(version),'failed')
            self.assertEqual(version.jobs.get().safe_error_code,'invalid_or_unsupported_image')
            self.assertEqual(storage.read_original(version),data)
            self.assertFalse(ImageInspection.objects.filter(source_version=version).exists())

    def test_mismatched_dicom_uid_fails_without_confirming_header(self):
        data=dicom().replace(b'1.2.826.0.1.3680043.8.498.1001',b'1.2.826.0.1.3680043.8.498.9999',1)
        version=self.upload('mismatch.dcm',data)
        self.assertEqual(self.process(version),'failed')
        self.assertEqual(version.metadata_head.revision,0)
        self.assertFalse(ImageInspection.objects.filter(source_version=version).exists())

    def test_raster_dimension_limit_preserves_original(self):
        data=raster()
        version=self.upload('limited.png',data)
        with patch('records.imaging.PIXEL_LIMIT',4):
            self.assertEqual(self.process(version),'failed')
        self.assertEqual(storage.read_original(version),data)
        self.assertFalse(ImageInspection.objects.filter(source_version=version).exists())

    def test_signature_extension_and_closed_kind(self):
        for name,data,kind in [('bad.dcm',raster(),'medical_image'),('x.png',raster(),'clinician'),('x.png',raster(),'medical_image')]:
            fields={'file':SimpleUploadedFile(name,data),'content_kind':kind}
            if name=='x.png' and kind=='medical_image':
                fields['workspace_id']=str(self.bob_workspace.pk)
            self.assertEqual(self.client.post(self.base+'records/',fields).status_code,400)

    def test_duplicate_different_kind_cannot_reclassify_original(self):
        version=self.upload('x.png',raster(),'document')
        changed=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('mri.png',raster()),'content_kind':'medical_image'})
        self.assertEqual(changed.status_code,409)
        version.refresh_from_db()
        self.assertEqual(version.content_kind,'document')

    def test_image_preview_survives_ocr_unavailable(self):
        version=self.upload('photographed-report.png',raster(),'document')
        self.assertEqual(self.process(version),'needs_ocr')
        self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/preview/').status_code,200)

    def test_processing_checks_read_and_upload_revocation(self):
        version=self.upload('scan.dcm',dicom())
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='upload_source').update(revoked_at=timezone.now())
        self.assertEqual(self.process(version),'failed')
        self.assertFalse(ImageInspection.objects.filter(source_version=version).exists())

    def test_preview_is_bounded_and_strips_exif(self):
        image=Image.new('RGB',(1000,900),'white')
        exif=Image.Exif()
        exif[315]='PRIVATE-EXIF-FIXTURE'
        data=BytesIO()
        image.save(data,format='JPEG',exif=exif)
        version=self.upload('scan.jpg',data.getvalue())
        self.assertEqual(self.process(version),'manual_review')
        preview=bytes(version.image_inspection.preview_png)
        self.assertNotIn(b'PRIVATE-EXIF-FIXTURE',preview)
        self.assertLessEqual(len(preview),1024*1024)
        self.assertLessEqual(max(Image.open(BytesIO(preview)).size),512)

    def test_selected_image_and_report_packet_keeps_source_ids(self):
        from records.tests.test_backend import pdf
        image=self.upload('study.dcm',dicom())
        report=self.upload('radiology-report.pdf',pdf('Synthetic radiology report'),'document')
        self.process(image)
        services.review(self.alice,self.workspace.pk,image.record_id,{'document_type':'medical_image','document_date':UNKNOWN_DATE,'facility_name':None},0,image.pk)
        packet=services.create_packet(self.alice,self.workspace.pk,'Synthetic imaging consultation',[str(image.pk),str(report.pk)])
        result=self.client.get(self.base+f'packets/{packet.pk}/').json()
        self.assertEqual({item['source_version']['id'] for item in result['items']},{str(image.pk),str(report.pk)})

    @skipUnless(connection.vendor=='postgresql','PostgreSQL guards')
    def test_image_inspection_workspace_and_history_guards(self):
        version=self.upload('scan.dcm',dicom())
        self.process(version)
        inspection=version.image_inspection
        with self.assertRaises(IntegrityError),transaction.atomic():
            ImageInspection.objects.filter(pk=inspection.pk).update(details={})
        with self.assertRaises(IntegrityError),transaction.atomic():
            IngestionJob.objects.filter(source_version=version).update(state='queued')
        uninspected=self.upload('other.dcm',dicom('US'))
        with self.assertRaises(IntegrityError),transaction.atomic():
            ImageInspection.objects.create(workspace=self.bob_workspace,source_version=uninspected,inspector_version='fixture',details={'format':'DICOM'})

    @skipUnless(connection.vendor=='postgresql','PostgreSQL inspection source guard')
    def test_inspection_cannot_be_attached_to_pdf(self):
        from records.tests.test_backend import pdf
        version=self.upload('report.pdf',pdf(),'document')
        with self.assertRaises(IntegrityError),transaction.atomic():
            ImageInspection.objects.create(workspace=self.workspace,source_version=version,inspector_version='fixture',details={'format':'DICOM'})

    @skipUnless(connection.vendor=='postgresql','PostgreSQL runtime role')
    def test_inspection_under_runtime_database_role(self):
        from identity.db_roles import configure_runtime_permissions
        configure_runtime_permissions(connection)
        version=self.upload('scan.dcm',dicom())
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET ROLE continuity_app')
            self.assertEqual(self.process(version),'manual_review')
            self.assertEqual(self.client.get(self.base+f'versions/{version.pk}/image/').status_code,200)
        finally:
            with connection.cursor() as cursor:
                cursor.execute('RESET ROLE')
