import json
import time
from unittest import skipUnless
from django.db import IntegrityError,connection,transaction
from django.test import Client,TestCase
from django.utils import timezone
from identity.models import (AccessCapability,AuditEvent,CareCircleEntry,OIDCIdentity,PatientPersonalDetails,PatientWorkspace)
from identity.services import resolve_verified_identity

PROFILE={'full_name':'Fictional Patient','preferred_name':'Demo','email':'patient.profile@example.invalid','phone':'+000 123456',
    'address':'Fictional address','gender':'','identifier_type':'national_id','identifier_number':'FICTIONAL-ID-001',
    'identifier_issuer':'Demo issuer','blood_group':'O+',
    'birth_date':{'precision':'month','year':1990,'month':8,'day':None}}
CONTACT={'full_name':'Fictional Relative','relationship':'guardian','email':'relative@example.invalid','phone':'+000 987654',
    'notes':'Fictional contact only','is_next_of_kin':True,'is_emergency_contact':True,'recipient_id':None}


class ProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice=resolve_verified_identity('https://test.example/issuer','profile-alice','Profile Alice')
        cls.bob=resolve_verified_identity('https://test.example/issuer','profile-bob','Profile Bob')
        cls.workspace=PatientWorkspace.objects.get(subject_patient__person=cls.alice.person)

    def setUp(self):
        self.sign_in(self.alice)
        self.base=f'/api/workspaces/{self.workspace.pk}/'

    def sign_in(self,user,client=None):
        client=client or self.client; client.force_login(user,backend='identity.backends.OIDCSessionBackend')
        session=client.session; session['oidc_expires_at']=int(time.time())+300; session.save()

    def post(self,path,data,client=None):
        return (client or self.client).post(path,data=json.dumps(data),content_type='application/json')

    def contact(self,values=None):
        response=self.post(self.base+'care-circle/',{'values':values or CONTACT,'expected_revision':0})
        self.assertEqual(response.status_code,201,response.content)
        return response.json()

    def test_profile_partial_birth_and_sensitive_fields_preserved_without_identity_relink(self):
        identity=OIDCIdentity.objects.get(user=self.alice)
        response=self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':0})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['values'],PROFILE)
        self.assertEqual(response.json()['revision'],1)
        self.alice.person.refresh_from_db()
        self.assertEqual(self.alice.person.birth_date_precision,'month')
        self.assertIsNone(self.alice.person.birth_day)
        identity.refresh_from_db()
        self.assertEqual(identity.subject,'profile-alice')
        self.assertEqual(identity.user_id,self.alice.pk)
        self.assertEqual(self.alice.person.display_name,'Profile Alice')
        self.assertTrue(AuditEvent.objects.filter(action='profile.save',actor_user=self.alice).exists())
        audit=json.dumps(list(AuditEvent.objects.values()),default=str)
        self.assertNotIn(PROFILE['identifier_number'],audit)
        self.assertNotIn(PROFILE['email'],audit)
        headers=self.client.get(self.base+'profile/').headers
        self.assertIn('no-store',headers['Cache-Control'])

    def test_profile_optimistic_revision_rejects_stale_save(self):
        self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':0})
        response=self.post(self.base+'profile/',{'values':{**PROFILE,'phone':'new'},'expected_revision':0})
        self.assertEqual(response.status_code,409)
        self.assertEqual(PatientPersonalDetails.objects.get().phone,PROFILE['phone'])
        self.assertEqual(self.post(self.base+'profile/',{'values':{**PROFILE,'phone':'new'},'expected_revision':1}).status_code,200)

    def test_profile_validation_rejects_bad_calendar_email_blood_group_and_id_shape(self):
        for changes in ({'blood_group':'invented'},{'email':'not an email'},
                        {'identifier_type':'none'},{'birth_date':{'precision':'day','year':2025,'month':2,'day':30}},
                        {'birth_date':{'precision':'year','year':1990,'month':1,'day':None}}):
            self.assertEqual(self.post(self.base+'profile/',{'values':{**PROFILE,**changes},'expected_revision':0}).status_code,400)
        self.assertFalse(PatientPersonalDetails.objects.exists())

    def test_unrelated_recipient_cannot_read_profile_contacts_or_page(self):
        self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':0})
        self.contact()
        self.sign_in(self.bob)
        for path in ('profile/','care-circle/','care-circle/choices/'):
            response=self.client.get(self.base+path)
            self.assertEqual(response.status_code,404)
            self.assertNotIn(PROFILE['identifier_number'].encode(),response.content)
        self.assertEqual(self.client.get(f'/workspaces/{self.workspace.pk}/profile/').status_code,404)
        self.assertEqual(self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':1}).status_code,404)

    def test_saved_guardian_contact_does_not_create_membership_capability_or_email_link(self):
        before=self.bob.workspace_memberships.count()
        entry=self.contact({**CONTACT,'email':PROFILE['email']})
        self.assertIsNone(entry['values']['recipient_id'])
        self.assertEqual(self.bob.workspace_memberships.count(),before)
        self.assertFalse(AccessCapability.objects.filter(workspace=self.workspace,membership__user=self.bob).exists())
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base+'records/').status_code,404)

    def test_exact_link_and_care_circle_picker_include_only_active_account_contacts(self):
        unlinked=self.contact()
        entry=self.contact({**CONTACT,'full_name':'Linked fictional friend','relationship':'friend','recipient_id':str(self.bob.pk)})
        choices=self.client.get(self.base+'care-circle/choices/').json()['contacts']
        self.assertEqual([c['recipient_id'] for c in choices],[str(self.bob.pk)])
        self.assertNotIn('email',choices[0]); self.assertNotIn('phone',choices[0])
        self.assertEqual(self.post(self.base+'care-circle/',{'values':{**CONTACT,'recipient_id':str(self.bob.pk)},'expected_revision':0}).status_code,409)
        self.bob.is_active=False; self.bob.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(self.base+'care-circle/choices/').json()['contacts'],[])

    def test_contact_edit_archive_restore_and_conflicts(self):
        entry=self.contact(); key=entry['id']
        response=self.post(self.base+f'care-circle/{key}/',{'values':{**CONTACT,'phone':'changed'},'expected_revision':1})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.post(self.base+f'care-circle/{key}/status/',{'status':'archived','expected_revision':1}).status_code,409)
        self.assertEqual(self.post(self.base+f'care-circle/{key}/status/',{'status':'archived','expected_revision':2}).status_code,200)
        self.assertEqual(self.client.get(self.base+'care-circle/').json()['contacts'],[])
        self.assertEqual(len(self.client.get(self.base+'care-circle/?include_archived=1').json()['contacts']),1)
        self.assertEqual(self.post(self.base+f'care-circle/{key}/status/',{'status':'active','expected_revision':3}).status_code,200)
        self.assertEqual(CareCircleEntry.objects.get(pk=key).revision,4)

    def test_missing_profile_capability_and_csrf_deny_writes(self):
        client=Client(enforce_csrf_checks=True); self.sign_in(self.alice,client)
        self.assertEqual(self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':0},client).status_code,403)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_profile').update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(self.base+'profile/').status_code,404)
        self.assertEqual(self.post(self.base+'care-circle/',{'values':CONTACT,'expected_revision':0}).status_code,404)

    @skipUnless(connection.vendor=='postgresql','Native profile scope/revision/editor guards')
    def test_database_profile_and_contact_bindings_cannot_be_rewritten(self):
        self.post(self.base+'profile/',{'values':PROFILE,'expected_revision':0})
        contact=self.contact(); profile=PatientPersonalDetails.objects.get()
        for model,key in ((PatientPersonalDetails,profile.pk),(CareCircleEntry,contact['id'])):
            with self.assertRaises(IntegrityError),transaction.atomic():
                model.objects.filter(pk=key).update(updated_by=self.bob,revision=2)
            with self.assertRaises(IntegrityError),transaction.atomic():
                model.objects.filter(pk=key).update(revision=8)
