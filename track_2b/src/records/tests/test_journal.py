import json
from datetime import timedelta
from unittest import skipUnless
from django.db import connection, IntegrityError, DatabaseError, transaction
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone
from identity.models import AccessCapability
from identity.db_roles import configure_runtime_permissions
from records.models import JournalEvent, JournalHistory, JournalDraft, PatientHealthConcern, AssistantSource, PacketSourceItem
from records import journal
from . import test_backend

VALUES={'category':'note','description':'Fictional note: headache this afternoon.',
    'occurrence':{'precision':'day','year':2026,'month':10,'day':16},'time':None,
    'timezone':'Africa/Nairobi','fold':None,'severity':None,'concern_id':None}
DRAFT={'category':'note','description':VALUES['description'],'precision':'day','year':'2026','month':'10','day':'16',
    'time':'','timezone':'Africa/Nairobi','fold':'','severity':'','concern_id':''}


class JournalTests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in
    upload=test_backend.BackendTests.upload

    def post(self,path,data):
        return self.client.post(self.base+'journal/'+path,json.dumps(data),content_type='application/json')

    def save(self,values=None,key=None,rev=0,draft=None):
        return self.post(str(key)+'/' if key else '',{'values':values or VALUES,'expected_revision':rev,'draft_revision':draft})

    def test_note_survives_session_and_has_no_disclosure_side_effect(self):
        response=self.save(); self.assertEqual(response.status_code,201,response.content)
        item=response.json(); self.assertEqual(item['visibility'],'private'); self.assertEqual(item['provenance'],'patient_reported')
        self.client.logout(); self.sign_in(self.alice)
        self.assertEqual(self.client.get(self.base+'journal/'+item['id']+'/').json()['values'],VALUES)
        self.assertEqual(AssistantSource.objects.count(),0); self.assertEqual(PacketSourceItem.objects.count(),0)

    def test_symptom_optional_severity_and_validation(self):
        for severity in (None,0,10):
            self.assertEqual(self.save({**VALUES,'category':'symptom','severity':severity}).status_code,201)
        for changes in ({'severity':5},{'category':'symptom','severity':11},{'category':'symptom','severity':True},
            {'description':'  '},{'category':'medication'},{'verified':True},
            {'occurrence':{'precision':'day','year':2026,'month':2,'day':30}}):
            self.assertEqual(self.save({**VALUES,**changes}).status_code,400)

    def test_cross_patient_and_revoked_authority_denied(self):
        item=self.save().json(); self.sign_in(self.bob)
        for suffix in ('',item['id']+'/',item['id']+'/history/','draft/'):
            self.assertEqual(self.client.get(self.base+'journal/'+suffix).status_code,404)
        self.assertEqual(self.save(key=item['id'],rev=1).status_code,404)
        self.assertEqual(self.post(item['id']+'/status/',{'status':'archived','expected_revision':1}).status_code,404)
        self.sign_in(self.alice)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_profile').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+'journal/draft/').status_code,404)

    def test_concern_scope_and_archived_associations(self):
        foreign=PatientHealthConcern.objects.create(workspace=self.bob_workspace,updated_by=self.bob,title='Fictional concern')
        self.assertEqual(self.save({**VALUES,'concern_id':str(foreign.pk)}).status_code,404)
        own=PatientHealthConcern.objects.create(workspace=self.workspace,updated_by=self.alice,title='Fictional concern')
        values={**VALUES,'concern_id':str(own.pk)}
        item=self.save(values).json()
        own.status='archived'; own.revision+=1; own.save()
        self.assertEqual(self.save(values,item['id'],1).status_code,200)
        self.assertEqual(self.save(values).status_code,409)

    @skipUnless(connection.vendor=='postgresql','Database-generated revision history')
    def test_edit_history_stale_revision_archive_restore(self):
        item=self.save().json()
        self.assertEqual(self.save({**VALUES,'description':'Correction'},item['id'],1).status_code,200)
        self.assertEqual(self.save(key=item['id'],rev=1).status_code,409)
        rows=self.client.get(self.base+'journal/'+item['id']+'/history/').json()['history']
        self.assertEqual([row['revision'] for row in rows],[2,1]); self.assertEqual(rows[1]['snapshot']['description'],VALUES['description'])
        self.assertEqual(self.post(item['id']+'/status/',{'status':'archived','expected_revision':2}).status_code,200)
        self.assertEqual(self.save(key=item['id'],rev=3).status_code,409)
        self.assertEqual(self.post(item['id']+'/status/',{'status':'active','expected_revision':3}).status_code,200)
        self.assertEqual(JournalHistory.objects.count(),4)

    def test_time_zone_dst_gap_and_fold(self):
        values={**VALUES,'timezone':'Europe/Zurich','time':'02:30','occurrence':{'precision':'day','year':2026,'month':3,'day':29}}
        self.assertEqual(self.save(values).json()['error'],'journal_nonexistent_time')
        values['occurrence']={'precision':'day','year':2026,'month':10,'day':25}
        self.assertEqual(self.save(values).json()['error'],'journal_ambiguous_time')
        first=self.save({**values,'fold':0}).json(); second=self.save({**values,'fold':1}).json()
        self.assertNotEqual(first['occurred_at'],second['occurred_at']); self.assertEqual(first['values']['time'],'02:30')
        self.assertEqual(self.save({**VALUES,'timezone':'Made/Up'}).status_code,400)
        self.assertEqual(self.save({**VALUES,'time':'12:30','occurrence':{'precision':'year','year':2026,'month':None,'day':None}}).status_code,400)

    @skipUnless(connection.vendor=='postgresql','Bounded date projection uses PostgreSQL')
    def test_range_partial_unknown_filters_and_pagination(self):
        for index in range(32): self.assertEqual(self.save({**VALUES,'description':str(index)}).status_code,201)
        self.save({**VALUES,'occurrence':{'precision':'year','year':2026,'month':None,'day':None}})
        unknown=self.save({**VALUES,'occurrence':{'precision':'unknown','year':None,'month':None,'day':None}}).json()
        path=self.base+'journal/?from=2026-10-01&to=2026-10-31'
        response=self.client.get(path).json(); self.assertEqual(len(response['items']),30); self.assertEqual(response['next_page'],2)
        rest=self.client.get(path+'&page=2').json()['items']; self.assertEqual(len(rest),3)
        partial=next(row for row in response['items']+rest if row['values']['occurrence']['precision']=='year')
        self.assertIsNone(partial['values']['occurrence']['month'])
        self.assertNotIn(unknown['id'],[row['id'] for row in response['items']+rest])
        self.assertEqual(self.client.get(path+'&undated=true&page=2').status_code,200)
        self.assertEqual(self.client.get(path+'&category=symptom').json()['items'],[])
        self.assertEqual(self.client.get(self.base+'journal/?from=2020-01-01&to=2026-10-31').status_code,400)

    def test_recovery_draft_private_stale_and_atomic_publish(self):
        data={'fields':DRAFT,'expected_revision':0,'event_id':None,'base_revision':0}
        draft=self.post('draft/',data).json()['draft']
        self.assertEqual(JournalEvent.objects.count(),0)
        self.assertEqual(self.post('draft/',data).status_code,409)
        self.client.logout(); self.sign_in(self.alice)
        self.assertEqual(self.client.get(self.base+'journal/draft/').json()['draft']['fields'],DRAFT)
        self.assertEqual(self.save(draft=draft['revision']).status_code,201)
        self.assertEqual(JournalDraft.objects.count(),0)
        self.assertEqual(self.save(draft=draft['revision']).status_code,409)
        self.assertEqual(JournalEvent.objects.count(),1)

    def test_draft_validation_discard_and_never_published_on_expiry(self):
        data={'fields':{**DRAFT,'description':''},'expected_revision':0,'event_id':None,'base_revision':0}
        draft=self.post('draft/',data).json()['draft']
        self.assertEqual(self.post('draft/discard/',{'expected_revision':99}).status_code,409)
        session=self.client.session; session['oidc_expires_at']=int((timezone.now()-timedelta(seconds=1)).timestamp()); session.save()
        self.assertEqual(self.client.get(self.base+'journal/draft/').status_code,401)
        self.assertEqual(JournalEvent.objects.count(),0)
        self.sign_in(self.alice)
        self.assertEqual(self.post('draft/discard/',{'expected_revision':draft['revision']}).status_code,200)
        self.assertEqual(self.post('draft/',{**data,'fields':{**DRAFT,'unknown':'secret'}}).status_code,400)

    def test_csrf_and_no_store(self):
        client=Client(enforce_csrf_checks=True); self.sign_in(self.alice,client)
        self.assertEqual(client.post(self.base+'journal/',json.dumps({'values':VALUES,'expected_revision':0,'draft_revision':None}),content_type='application/json').status_code,403)
        self.assertEqual(self.client.get(self.base+'journal/draft/')['Cache-Control'],'no-store, private')

    def test_record_share_recipient_has_no_journal_or_draft_access(self):
        from records import services, continuity
        version=self.upload()
        packet=services.create_packet(self.alice,self.workspace.pk,'Fictional test only',[str(version.pk)])
        continuity.create_grant(self.alice,self.workspace.pk,'read',packet.revisions.get().pk,self.bob.pk,'Fictional test',60)
        item=self.save().json()
        self.post('draft/',{'fields':DRAFT,'expected_revision':0,'event_id':None,'base_revision':0})
        self.sign_in(self.bob)
        for suffix in ('',item['id']+'/',item['id']+'/history/','draft/'):
            self.assertEqual(self.client.get(self.base+'journal/'+suffix).status_code,404)

    def test_bad_draft_bindings_and_sensitive_fields_are_rejected(self):
        item=self.save().json()
        data={'fields':DRAFT,'expected_revision':0,'event_id':item['id'],'base_revision':0}
        self.assertEqual(self.post('draft/',data).status_code,400)
        for fields in ({**DRAFT,'description':'x'*2001},{**DRAFT,'severity':False},{**DRAFT,'author_id':str(self.bob.pk)}):
            self.assertEqual(self.post('draft/',{**data,'event_id':None,'fields':fields}).status_code,400)
        self.sign_in(self.bob); self.base=f'/api/workspaces/{self.bob_workspace.pk}/'
        self.assertEqual(self.post('draft/',{**data,'base_revision':1}).status_code,404)

    @skipUnless(connection.vendor=='postgresql','SQL constraints, history and runtime role')
    def test_database_guards_and_runtime_history_privileges(self):
        item=journal.save(self.alice,self.workspace.pk,VALUES,0)
        foreign=PatientHealthConcern.objects.create(workspace=self.bob_workspace,updated_by=self.bob,title='Foreign fictional concern')
        for changes in ({'workspace':self.bob_workspace,'revision':2},{'updated_by':self.bob,'revision':2},
            {'revision':4},{'severity':8,'revision':2},{'created_by':self.bob,'revision':2},
            {'concern_id':foreign.pk,'revision':2},
            {'occurrence':{'precision':'day','year':2026,'month':2,'day':30},'revision':2},
            {'timezone_name':'Made/Up','revision':2}):
            with self.assertRaises(IntegrityError),transaction.atomic(): JournalEvent.objects.filter(pk=item.pk).update(**changes)
        with self.assertRaises(IntegrityError),transaction.atomic(): JournalEvent.objects.filter(pk=item.pk).delete()
        with self.assertRaises(IntegrityError),transaction.atomic(): JournalHistory.objects.filter(event=item).update(snapshot={})
        configure_runtime_permissions(connection)
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL ROLE continuity_app')
        try:
            saved=journal.save(self.alice,self.workspace.pk,{**VALUES,'description':'Runtime write'},1,item.pk)
            self.assertEqual(saved.history.count(),2)
            with self.assertRaises(DatabaseError),transaction.atomic():
                JournalHistory.objects.create(workspace=self.workspace,event=item,revision=3,actor=self.alice,snapshot={})
        finally:
            with connection.cursor() as cursor: cursor.execute('RESET ROLE')


@skipUnless(connection.vendor=='postgresql','Native migration reversal')
class JournalMigrationTests(TransactionTestCase):
    def setUp(self):
        # TransactionTestCase flushes migration-seeded catalogue data between classes.
        from identity.authorization import SELF_ACTIONS
        from identity.models import CapabilityRule
        for action in SELF_ACTIONS:
            CapabilityRule.objects.get_or_create(authority_kind='membership',capability_key=action,scope_kind='workspace')

    def test_forward_reverse_preserves_existing_record_tables(self):
        from django.db.migrations.executor import MigrationExecutor
        latest=MigrationExecutor(connection).loader.graph.leaf_nodes()
        from identity.services import resolve_verified_identity
        from identity.models import PatientWorkspace
        from records.models import SourceRecord
        user=resolve_verified_identity('https://test.example/issuer','journal-migration','Fictional migration patient')
        workspace=PatientWorkspace.objects.get(subject_patient__person=user.person)
        record=SourceRecord.objects.create(workspace=workspace,submitted_by=user)
        journal.save(user,workspace.pk,VALUES,0)
        try:
            MigrationExecutor(connection).migrate([('records','0015_journal_foundation')])
            self.assertEqual(JournalEvent.objects.count(),1)
            MigrationExecutor(connection).migrate([('records','0014_care_guards')])
            self.assertTrue(SourceRecord.objects.filter(pk=record.pk).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
            configure_runtime_permissions(connection)
        self.assertTrue(SourceRecord.objects.filter(pk=record.pk).exists())
        self.assertEqual(JournalEvent.objects.count(),0)
