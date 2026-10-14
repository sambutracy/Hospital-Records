import json
from unittest import skipUnless
from django.db import IntegrityError,connection,transaction
from django.test import TestCase
from django.utils import timezone
from identity.models import AccessCapability
from records import continuity
from records.models import MedicationEntry,SourceVersion
from . import test_backend

VALUES={'medicine_name':'Fictional medicine','dose':'as written on fictional label','frequency':'as written',
        'route':'','instructions':'Fictional test only','use_status':'reported_prescribed',
        'visit_date':{'precision':'month','year':2026,'month':9,'day':None},'episode_id':None,'source_version_id':None}


class MedicationTests(TestCase):
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in
    upload=test_backend.BackendTests.upload

    @classmethod
    def setUpTestData(cls):
        test_backend.BackendTests.setUpTestData.__func__(cls)

    def post(self,path,data):
        return self.client.post(path,data=json.dumps(data),content_type='application/json')

    def save(self,values=None):
        response=self.post(self.base+'medications/',{'values':values or VALUES,'expected_revision':0})
        self.assertEqual(response.status_code,201,response.content)
        return response.json()

    def test_two_visit_entries_keep_taken_and_prescribed_distinct(self):
        first=self.save()
        second=self.save({**VALUES,'use_status':'reported_taken','visit_date':{'precision':'year','year':2025,'month':None,'day':None}})
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['values']['use_status'],'reported_prescribed')
        self.assertEqual(second['values']['use_status'],'reported_taken')
        self.assertIsNone(first['values']['visit_date']['day'])
        self.assertIsNone(second['values']['visit_date']['month'])
        self.assertEqual(len(self.client.get(self.base+'medications/').json()['medications']),2)

    def test_source_and_episode_links_preserve_exact_original(self):
        original=self.upload()
        episode=continuity.create_episode(self.alice,self.workspace.pk,'Medication visit context')
        entry=self.save({**VALUES,'episode_id':str(episode.pk),'source_version_id':str(original.pk)})
        replacement=self.upload('Different fictional prescription',original.record)
        saved=MedicationEntry.objects.get(pk=entry['id'])
        self.assertEqual(saved.source_version_id,original.pk)
        self.assertNotEqual(saved.source_version_id,replacement.pk)
        self.assertEqual(SourceVersion.objects.get(pk=original.pk).sha256,original.sha256)
        choices=self.client.get(self.base+'medications/choices/').json()
        self.assertEqual(len(choices['sources']),2)

    def test_cross_workspace_links_and_unrelated_reads_writes_denied(self):
        self.sign_in(self.bob)
        previous=self.base; self.base=f'/api/workspaces/{self.bob_workspace.pk}/'
        source=self.upload(); episode=continuity.create_episode(self.bob,self.bob_workspace.pk,'Bob visit')
        self.base=previous; self.sign_in(self.alice)
        for links in ({'source_version_id':str(source.pk)},{'episode_id':str(episode.pk)}):
            self.assertEqual(self.post(self.base+'medications/',{'values':{**VALUES,**links},'expected_revision':0}).status_code,404)
        entry=self.save(); self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+'medications/').status_code,404)
        self.assertEqual(self.post(self.base+f"medications/{entry['id']}/",{'values':VALUES,'expected_revision':1}).status_code,404)
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/medications/').status_code,404)

    def test_validation_and_stale_revisions(self):
        for changes in ({'medicine_name':''},{'use_status':'verified'},{'visit_date':{'precision':'day','year':2026,'month':2,'day':30}}):
            self.assertEqual(self.post(self.base+'medications/',{'values':{**VALUES,**changes},'expected_revision':0}).status_code,400)
        entry=self.save()
        self.assertEqual(self.post(self.base+f"medications/{entry['id']}/",{'values':VALUES,'expected_revision':0}).status_code,409)
        self.assertEqual(self.post(self.base+f"medications/{entry['id']}/",{'values':{**VALUES,'use_status':'reported_taken'},'expected_revision':1}).status_code,200)

    def test_archive_restore_and_medication_permission_revocation(self):
        entry=self.save(); key=entry['id']
        self.assertEqual(self.post(self.base+f'medications/{key}/status/',{'status':'archived','expected_revision':1}).status_code,200)
        self.assertEqual(self.client.get(self.base+'medications/').json()['medications'],[])
        self.assertEqual(len(self.client.get(self.base+'medications/?include_archived=1').json()['medications']),1)
        self.assertEqual(self.post(self.base+f'medications/{key}/status/',{'status':'active','expected_revision':2}).status_code,200)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_medications').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+'medications/').status_code,404)

    @skipUnless(connection.vendor=='postgresql','Native medication scope/calendar/editor guards')
    def test_database_rejects_wrong_editor_invalid_calendar_and_revision(self):
        entry=self.save(); key=entry['id']
        for changes in ({'updated_by':self.bob,'revision':2},{'revision':7},
                        {'date_precision':'day','value_year':2026,'value_month':2,'value_day':30,'revision':2}):
            with self.assertRaises(IntegrityError),transaction.atomic():
                MedicationEntry.objects.filter(pk=key).update(**changes)
