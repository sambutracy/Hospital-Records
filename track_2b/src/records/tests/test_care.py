import json
from unittest import skipUnless
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, Client
from django.utils import timezone
from identity.models import AccessCapability, User, WorkspaceMembership
from identity.authorization import authorized_workspaces
from identity.db_roles import configure_runtime_permissions
from records.models import (PatientHealthConcern, ReportedPractitioner, CareTeamAssignment,
    CareHistory, ShareGrant, ProviderContributionAuthority)
from records.metadata import UNKNOWN_DATE
from . import test_backend

CONCERN={'title':'Fictional follow-up investigation','description':'Patient-reported test concern',
    'kind':'investigation','certainty':'unconfirmed','onset':{'precision':'year','year':2025,'month':None,'day':None}}
DOCTOR={'name':'Dr Fictional Cedar','specialty':'General practice','facility':'Fictional Cedar Clinic','notes':''}


class CareTests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in

    def post(self, suffix, values):
        return self.client.post(self.base+'care/'+suffix, json.dumps(values), content_type='application/json')

    def save(self, kind, values, revision=0, key=None):
        response=self.post(kind+'/' +(key+'/' if key else ''), {'values':values,'expected_revision':revision})
        self.assertEqual(response.status_code,200 if key else 201,response.content)
        return response.json()

    def relationship(self, doctor, concern=None):
        return {'practitioner_id':doctor['id'],'concern_id':concern['id'] if concern else None,'role':'Historical doctor',
            'participation':'historical','start_date':{'precision':'month','year':2025,'month':9,'day':None},
            'end_date':UNKNOWN_DATE,'notes':'Test only'}

    def test_concern_doctor_link_is_patient_reported_and_never_grants_authority(self):
        counts=(User.objects.count(),WorkspaceMembership.objects.count(),AccessCapability.objects.count())
        concern=self.save('concerns',CONCERN); doctor=self.save('practitioners',{**DOCTOR,'name':self.bob.person.display_name})
        assignment=self.save('assignments',self.relationship(doctor,concern))
        self.assertEqual(assignment['access_effect'],'none'); self.assertEqual(concern['provenance'],'patient_reported')
        self.assertEqual(concern['values']['certainty'],'unconfirmed')
        self.assertIsNone(concern['values']['onset']['month']); self.assertIsNone(assignment['values']['start_date']['day'])
        self.assertEqual(counts,(User.objects.count(),WorkspaceMembership.objects.count(),AccessCapability.objects.count()))
        self.assertEqual(ShareGrant.objects.count(),0); self.assertEqual(ProviderContributionAuthority.objects.count(),0)
        self.assertNotIn(self.workspace.pk,list(authorized_workspaces(self.bob).values_list('pk',flat=True)))
        self.sign_in(self.bob)
        for route in ('care/concerns/','care/practitioners/','care/assignments/','records/'):
            self.assertEqual(self.client.get(self.base+route).status_code,404)

    def test_cross_patient_links_reads_edits_history_and_status_denied(self):
        concern=self.save('concerns',CONCERN); doctor=self.save('practitioners',DOCTOR)
        base=self.base; self.sign_in(self.bob); self.base=f'/api/workspaces/{self.bob_workspace.pk}/'
        other=self.save('practitioners',DOCTOR)
        self.assertEqual(self.post('assignments/',{'values':self.relationship(doctor,concern),'expected_revision':0}).status_code,404)
        values=self.relationship(other,concern)
        self.assertEqual(self.post('assignments/',{'values':values,'expected_revision':0}).status_code,404)
        self.base=base
        for suffix in (f"concerns/{concern['id']}/history/",'concerns/'):
            self.assertEqual(self.client.get(self.base+'care/'+suffix).status_code,404)
        self.assertEqual(self.post(f"concerns/{concern['id']}/",{'values':CONCERN,'expected_revision':1}).status_code,404)
        self.assertEqual(self.post(f"concerns/{concern['id']}/status/",{'status':'archived','expected_revision':1}).status_code,404)

    @skipUnless(connection.vendor=='postgresql','Authoritative immutable snapshots are PostgreSQL-backed')
    def test_revisions_history_archive_restore_and_stale_edits(self):
        concern=self.save('concerns',CONCERN)
        updated=self.save('concerns',{**CONCERN,'title':'Corrected fictional concern'},1,concern['id'])
        self.assertEqual(updated['revision'],2)
        self.assertEqual(self.post(f"concerns/{concern['id']}/",{'values':CONCERN,'expected_revision':1}).status_code,409)
        for revision,status in ((2,'archived'),(3,'active')):
            self.assertEqual(self.post(f"concerns/{concern['id']}/status/",{'status':status,'expected_revision':revision}).status_code,200)
        history=self.client.get(self.base+f"care/concerns/{concern['id']}/history/").json()['history']
        self.assertEqual([h['revision'] for h in history],[4,3,2,1])
        self.assertEqual(history[-1]['snapshot']['title'],CONCERN['title'])
        with self.assertRaises(IntegrityError),transaction.atomic():
            CareHistory.objects.filter(target_id=concern['id']).update(revision=10)
        with self.assertRaises(IntegrityError),transaction.atomic():
            PatientHealthConcern.objects.filter(pk=concern['id']).delete()

    def test_forged_verification_account_binding_bad_dates_and_empty_names_rejected(self):
        bad=[('concerns',{**CONCERN,'certainty':'clinician_verified'}),('concerns',{**CONCERN,'title':'  '}),
            ('concerns',{**CONCERN,'onset':{'precision':'day','year':2026,'month':2,'day':30}}),
            ('practitioners',{**DOCTOR,'recipient_id':str(self.bob.pk)}),('practitioners',{**DOCTOR,'verified':True})]
        for kind,values in bad:
            self.assertEqual(self.post(kind+'/',{'values':values,'expected_revision':0}).status_code,400)
        doctor=self.save('practitioners',DOCTOR)
        values=self.relationship(doctor)
        values['end_date']={'precision':'year','year':2024,'month':None,'day':None}
        self.assertEqual(self.post('assignments/',{'values':values,'expected_revision':0}).status_code,400)
        self.assertEqual(self.post('assignments/',{'values':{**self.relationship(doctor),'practitioner_id':'bad'},'expected_revision':0}).status_code,400)

    def test_duplicate_relationship_and_archived_parent_restoration(self):
        concern=self.save('concerns',CONCERN); doctor=self.save('practitioners',DOCTOR)
        values=self.relationship(doctor,concern); link=self.save('assignments',values)
        self.assertEqual(self.post('assignments/',{'values':values,'expected_revision':0}).status_code,409)
        self.assertEqual(self.post(f"assignments/{link['id']}/status/",{'status':'archived','expected_revision':1}).status_code,200)
        self.assertEqual(self.post(f"practitioners/{doctor['id']}/status/",{'status':'archived','expected_revision':1}).status_code,200)
        self.assertEqual(self.post(f"assignments/{link['id']}/status/",{'status':'active','expected_revision':2}).status_code,409)
        self.assertEqual(self.post('assignments/',{'values':values,'expected_revision':0}).status_code,404)

    def test_revocation_on_next_request_and_csrf_required(self):
        client=Client(enforce_csrf_checks=True); self.sign_in(self.alice,client)
        response=client.post(self.base+'care/concerns/',json.dumps({'values':CONCERN,'expected_revision':0}),content_type='application/json')
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.get(self.base+'care/concerns/')['Cache-Control'],'no-store, private')
        for action in ('manage_profile','read_workspace_records'):
            with transaction.atomic():
                cap=AccessCapability.objects.get(membership__user=self.alice,rule__capability_key=action)
                cap.revoked_at=timezone.now(); cap.save(update_fields=['revoked_at'])
                self.assertEqual(self.client.get(self.base+'care/concerns/').status_code,404)
                self.assertEqual(self.post('practitioners/',{'values':DOCTOR,'expected_revision':0}).status_code,404)
                transaction.set_rollback(True)

    @skipUnless(connection.vendor=='postgresql','Native workspace, actor, date and snapshot guards')
    def test_database_scope_actor_calendar_and_revision_guards(self):
        concern=self.save('concerns',CONCERN); doctor=self.save('practitioners',DOCTOR)
        for changes in ({'workspace':self.bob_workspace,'revision':2},{'updated_by':self.bob,'revision':2},
            {'revision':7},{'onset':{'precision':'day','year':2026,'month':2,'day':30},'revision':2},
            {'onset':{'precision':'unknown','year':None,'month':None,'day':None,'extra':1},'revision':2}):
            with self.assertRaises(IntegrityError),transaction.atomic():
                PatientHealthConcern.objects.filter(pk=concern['id']).update(**changes)
        foreign=ReportedPractitioner.objects.create(workspace=self.bob_workspace,updated_by=self.bob,**DOCTOR)
        with self.assertRaises(IntegrityError),transaction.atomic():
            CareTeamAssignment.objects.create(workspace=self.workspace,updated_by=self.alice,practitioner=foreign,role='Doctor')
        link=self.save('assignments',self.relationship(doctor,concern))
        with self.assertRaises(IntegrityError),transaction.atomic():
            CareTeamAssignment.objects.filter(pk=link['id']).update(end_date={'precision':'year','year':2024,'month':None,'day':None},revision=2)

    @skipUnless(connection.vendor=='postgresql','Runtime SQL role privilege boundary')
    def test_runtime_writes_generate_history_but_cannot_forge_or_remove_it(self):
        configure_runtime_permissions(connection)
        with connection.cursor() as cursor:
            for permission in ('INSERT','UPDATE','DELETE','TRUNCATE'):
                cursor.execute("SELECT has_table_privilege('continuity_app','care_history',%s)",[permission])
                self.assertFalse(cursor.fetchone()[0])
            cursor.execute('SET LOCAL ROLE continuity_app')
        try:
            item=ReportedPractitioner.objects.create(workspace=self.workspace,updated_by=self.alice,**DOCTOR)
            self.assertEqual(CareHistory.objects.filter(target_id=item.pk).count(),1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute('RESET ROLE')
