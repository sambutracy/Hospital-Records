from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from .test_backend import BackendTests,pdf,VALUES


class FrontendRecordsContractTests(TestCase):
    setUpTestData=classmethod(BackendTests.setUpTestData.__func__)
    setUp=BackendTests.setUp
    sign_in=BackendTests.sign_in
    def test_private_search_filters_retain_partial_dates_and_revision(self):
        version=self.client.post(self.base+'records/',{'file':SimpleUploadedFile('frontend-test.pdf',pdf(),content_type='application/pdf')}).json()['version']
        response=self.client.post(self.base+f"records/{version['record_id']}/review/",{'source_version_id':version['id'],'expected_revision':0,'values':VALUES},content_type='application/json')
        self.assertEqual(response.status_code,200)
        listing=self.client.post(self.base+'records/search/',{'q':'frontend-test','reviewed':'yes','document_year':2026,'document_type':'lab_report'},content_type='application/json').json()
        self.assertEqual(listing['total'],1); self.assertFalse(listing['has_more'])
        self.assertEqual(listing['records'][0]['metadata']['values']['document_date']['precision'],'month')
        self.assertEqual(self.client.post(self.base+'records/search/',{'reviewed':'no'},content_type='application/json').json()['total'],0)
        self.sign_in(self.bob)
        self.assertEqual(self.client.post(self.base+'records/search/',{'q':'frontend-test'},content_type='application/json').status_code,404)

    def test_private_search_rejects_unknown_filters_and_bad_dates(self):
        for payload in [{'diagnosis':'anything'},{'uploaded_from':'2026-02-30'},{'document_type':'invented'},{'offset':-1}]:
            self.assertEqual(self.client.post(self.base+'records/search/',payload,content_type='application/json').status_code,400)
