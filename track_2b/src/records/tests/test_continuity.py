from datetime import timedelta
import json
import time
from unittest import skipUnless
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.test import Client, TestCase
from django.utils import timezone
from identity.models import AccessCapability, AuditEvent, PatientWorkspace, User
from identity.services import resolve_verified_identity
from records import continuity
from records.models import (ClinicalContribution, EpisodeSource, IngestionJob,
                            ProviderContributionAuthority, ShareGrant, SourceRecord, SourceVersion)
from . import test_backend
from .test_backend import pdf, VALUES


class ContinuityTests(TestCase):
    setUp = test_backend.BackendTests.setUp
    sign_in = test_backend.BackendTests.sign_in
    upload = test_backend.BackendTests.upload
    confirm = test_backend.BackendTests.confirm

    @classmethod
    def setUpTestData(cls):
        test_backend.BackendTests.setUpTestData.__func__(cls)
        cls.clinician = resolve_verified_identity('https://test.example/issuer', 'invited-clinician', 'Invited clinician')

    def post(self, path, value, client=None):
        return (client or self.client).post(path, data=json.dumps(value), content_type='application/json')

    def make_grant(self, kind='read', minutes=60, clinician=None):
        version = self.upload()
        self.assertEqual(self.confirm(version).status_code, 200)
        episode = continuity.create_episode(self.alice, self.workspace.pk, 'Fictional follow-up')
        continuity.link_sources(self.alice, self.workspace.pk, episode.pk, [str(version.pk)])
        packet = self.post(self.base + 'packets/', {'purpose': 'Follow-up', 'source_version_ids': [str(version.pk)]}).json()
        grant = continuity.create_grant(self.alice, self.workspace.pk, kind,
            packet['revision_id'] if kind == 'read' else episode.pk,
            (clinician or self.clinician).pk, 'Review selected report' if kind == 'read' else 'Submit follow-up note', minutes)
        return grant, version, episode

    def clinician_client(self, user=None):
        client = Client()
        self.sign_in(user or self.clinician, client)
        return client

    def submit(self, grant, client=None, text='Fictional specialist consultation note'):
        return (client or self.clinician_client()).post(
            f'/api/continuity/contribution-authorities/{grant.pk}/submit/',
            {'file': SimpleUploadedFile('follow-up.pdf', pdf(text))})

    def test_exact_version_share_and_snapshot_survive_replacement(self):
        grant, original, _ = self.make_grant()
        unrelated = self.upload('Unrelated fictional record')
        replacement = self.upload('Corrected fictional report', original.record)
        self.assertEqual(self.confirm(replacement).status_code, 200)
        clinician = self.clinician_client()
        payload = clinician.get(f'/api/continuity/shares/{grant.pk}/').json()
        self.assertEqual([i['source_version_id'] for i in payload['items']], [str(original.pk)])
        self.assertEqual(payload['items'][0]['metadata']['document_date'], VALUES['document_date'])
        for source in (replacement, unrelated):
            self.assertEqual(clinician.get(f'/api/continuity/shares/{grant.pk}/versions/{source.pk}/original/').status_code, 404)
        response = clinician.get(payload['items'][0]['download_url'])
        self.assertEqual(b''.join(response.streaming_content), pdf())
        self.assertEqual(clinician.get(self.base + 'records/').status_code, 404)
        self.assertEqual(clinician.get(self.base + f'versions/{original.pk}/original/').status_code, 404)
        self.assertEqual(clinician.get(self.base + 'assistant/tasks/').status_code, 404)

    def test_wrong_recipient_and_read_grant_cannot_contribute(self):
        grant, version, _ = self.make_grant()
        self.assertEqual(self.clinician_client(self.bob).get(f'/api/continuity/shares/{grant.pk}/').status_code, 404)
        self.assertEqual(self.submit(grant).status_code, 404)
        self.assertFalse(ClinicalContribution.objects.exists())
        self.assertTrue(AuditEvent.objects.filter(action='continuity.submit_contribution', decision='deny').exists())

    def test_expiry_and_revocation_stop_open_session_reads(self):
        grant, version, _ = self.make_grant(minutes=1)
        client = self.clinician_client()
        route = f'/api/continuity/shares/{grant.pk}/versions/{version.pk}/original/'
        self.assertEqual(client.get(route).status_code, 200)
        with patch('records.continuity.timezone.now', return_value=grant.expires_at + timedelta(seconds=1)):
            self.assertEqual(client.get(route).status_code, 404)
        continuity.revoke(self.alice, self.workspace.pk, grant.pk, 'read')
        self.assertEqual(client.get(route).status_code, 404)
        self.assertEqual(client.get('/api/continuity/received/').json()['grants'], [])
        with self.assertRaises(Http404):
            continuity.revoke(self.bob, self.workspace.pk, grant.pk, 'read')

    def test_live_authorizer_capability_and_recipient_status_are_checked(self):
        grant, _, _ = self.make_grant()
        route = f'/api/continuity/shares/{grant.pk}/'
        client = self.clinician_client()
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='create_share').update(revoked_at=timezone.now())
        self.assertEqual(client.get(route).status_code, 404)
        self.assertEqual(client.get('/api/continuity/received/').json()['grants'], [])

    def test_disabled_recipient_and_revoked_parent_membership_stop_both_grants(self):
        grant, _, episode = self.make_grant()
        authority=continuity.create_grant(self.alice,self.workspace.pk,'contribute',episode.pk,self.clinician.pk,'Return note',60)
        client=self.clinician_client()
        User.objects.filter(pk=self.clinician.pk).update(is_active=False)
        self.assertEqual(client.get(f'/api/continuity/shares/{grant.pk}/').status_code,401)
        User.objects.filter(pk=self.clinician.pk).update(is_active=True)
        client=self.clinician_client()
        membership=grant.authorizing_membership
        membership.revoked_at=timezone.now()
        membership.save(update_fields=['revoked_at'])
        self.assertEqual(client.get(f'/api/continuity/shares/{grant.pk}/').status_code,404)
        self.assertEqual(self.submit(authority,client).status_code,404)

    def test_expired_or_independently_revoked_contribution_authority_denies_upload(self):
        authority, _, _=self.make_grant('contribute',minutes=1)
        with patch('records.continuity.timezone.now',return_value=authority.expires_at+timedelta(seconds=1)):
            self.assertEqual(self.submit(authority).status_code,404)
        continuity.revoke(self.alice,self.workspace.pk,authority.pk,'contribute')
        self.assertEqual(self.submit(authority).status_code,404)
        self.assertFalse(ClinicalContribution.objects.exists())

    def test_patient_isolation_and_explicit_grant_validation(self):
        grant, _, _ = self.make_grant()
        self.sign_in(self.bob)
        self.assertEqual(self.client.get(self.base + 'grants/').status_code, 404)
        self.assertEqual(self.client.get(self.base + 'contributions/').status_code, 404)
        self.sign_in(self.alice)
        for minutes in (0, 10081, True, '60'):
            response = self.post(self.base+'grants/', {'kind':'read','target_id':str(grant.packet_revision_id),
                'recipient_id':str(self.clinician.pk),'purpose':'Test','expires_in_minutes':minutes})
            self.assertEqual(response.status_code,400)

    def test_contribution_only_grant_no_read_and_pending_excluded_until_acceptance(self):
        authority, original, episode = self.make_grant('contribute')
        clinician = self.clinician_client()
        self.assertEqual(clinician.get(f'/api/continuity/shares/{authority.pk}/').status_code, 404)
        response = self.submit(authority, clinician)
        self.assertEqual(response.status_code,201,response.content)
        item_id = response.json()['id']
        self.assertEqual(self.submit(authority, clinician).status_code,200)
        self.assertEqual(SourceRecord.objects.filter(workspace=self.workspace).count(),1)
        self.assertEqual(IngestionJob.objects.filter(workspace=self.workspace).count(),1)
        self.assertEqual(len(self.client.get(self.base+'records/').json()['records']),1)
        self.assertEqual(clinician.get(self.base+'contributions/').status_code,404)
        self.assertEqual(self.post(self.base+f'contributions/{item_id}/review/',{'decision':'accept'},clinician).status_code,404)
        pending = self.client.get(self.base+f'contributions/{item_id}/original/')
        self.assertEqual(b''.join(pending.streaming_content),pdf('Fictional specialist consultation note'))
        continuity.revoke(self.alice,self.workspace.pk,authority.pk,'contribute')
        self.assertEqual(self.submit(authority,clinician,text='Second note').status_code,404)
        response = self.post(self.base+f'contributions/{item_id}/review/',{'decision':'accept'})
        self.assertEqual(response.status_code,200,response.content)
        item = ClinicalContribution.objects.get(pk=item_id)
        version = item.accepted_source
        self.assertEqual(version.submitted_by_id,self.clinician.pk)
        self.assertEqual(version.sha256,item.sha256)
        self.assertEqual(version.private_object_key,item.private_object_key)
        self.assertTrue(EpisodeSource.objects.filter(episode=episode,source_version=version).exists())
        self.assertEqual(version.jobs.get().requested_by_id,self.alice.pk)
        self.assertEqual(len(self.client.get(self.base+'records/').json()['records']),2)
        self.assertEqual(self.post(self.base+f'contributions/{item_id}/review/',{'decision':'accept'}).status_code,409)
        self.assertEqual(SourceVersion.objects.get(pk=original.pk).sha256,original.sha256)

    def test_rejected_note_never_enters_history_and_read_revoke_keeps_contribution_separate(self):
        read, _, _ = self.make_grant()
        episode = continuity.create_episode(self.alice,self.workspace.pk,'Separate return')
        authority = continuity.create_grant(self.alice,self.workspace.pk,'contribute',episode.pk,
            self.clinician.pk,'Return outcome',60)
        continuity.revoke(self.alice,self.workspace.pk,read.pk,'read')
        response = self.submit(authority)
        self.assertEqual(response.status_code,201)
        item_id=response.json()['id']
        self.assertEqual(self.post(self.base+f'contributions/{item_id}/review/',{'decision':'reject'}).status_code,200)
        self.assertEqual(SourceRecord.objects.filter(workspace=self.workspace).count(),1)
        self.assertFalse(ClinicalContribution.objects.get(pk=item_id).accepted_source_id)
        self.assertEqual(self.post(self.base+f'contributions/{item_id}/review/',{'decision':'accept'}).status_code,409)

    def test_episode_many_to_many_and_document_date_unknown_last(self):
        grant, first, episode = self.make_grant()
        second = self.upload('Year only record')
        self.confirm(second,{**VALUES,'document_date':{'precision':'year','year':2025,'month':None,'day':None}})
        unknown = self.upload('Unknown date record')
        other = continuity.create_episode(self.alice,self.workspace.pk,'Other episode')
        continuity.link_sources(self.alice,self.workspace.pk,other.pk,[str(first.pk)])
        rows=self.client.get(self.base+'records/?order=document_date').json()['records']
        self.assertEqual([r['id'] for r in rows],[str(first.record_id),str(second.record_id),str(unknown.record_id)])
        self.assertEqual(rows[1]['metadata']['values']['document_date']['precision'],'year')
        selected=self.client.get(self.base+f'records/?episode={other.pk}').json()['records']
        self.assertEqual([r['id'] for r in selected],[str(first.record_id)])
        self.assertEqual(EpisodeSource.objects.filter(source_version=first).count(),2)

    def test_csrf_protects_grant_and_contribution_actions(self):
        authority, _, _ = self.make_grant('contribute')
        client=Client(enforce_csrf_checks=True)
        self.sign_in(self.clinician,client)
        self.assertEqual(self.submit(authority,client).status_code,403)
        self.sign_in(self.alice,client)
        self.assertEqual(self.post(self.base+'episodes/',{'title':'No token'},client).status_code,403)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL integrity backstops')
    def test_database_rejects_cross_workspace_binding_and_grant_rewriting(self):
        grant, _, _ = self.make_grant()
        for changes in ({'recipient_id':self.bob.pk},{'purpose':'Changed'},{'expires_at':grant.expires_at+timedelta(days=1)}):
            with self.assertRaises(IntegrityError),transaction.atomic():
                ShareGrant.objects.filter(pk=grant.pk).update(**changes)
        episode=continuity.create_episode(self.bob,self.bob_workspace.pk,'Bob episode')
        with self.assertRaises(IntegrityError),transaction.atomic():
            ProviderContributionAuthority.objects.create(workspace=self.workspace,episode=episode,
                recipient=self.clinician,authorizing_membership=grant.authorizing_membership,
                purpose='Bad binding',expires_at=grant.expires_at)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL provenance and terminal state guards')
    def test_database_rejects_contribution_provenance_edit_and_clinician_acceptance(self):
        authority, _, _ = self.make_grant('contribute')
        response=self.submit(authority)
        item=ClinicalContribution.objects.get(pk=response.json()['id'])
        with self.assertRaises(IntegrityError),transaction.atomic():
            ClinicalContribution.objects.filter(pk=item.pk).update(original_filename='changed.pdf')
        with self.assertRaises(IntegrityError),transaction.atomic():
            ClinicalContribution.objects.filter(pk=item.pk).update(state='rejected',reviewed_by=self.clinician,reviewed_at=timezone.now())
        continuity.review_contribution(self.alice,self.workspace.pk,item.pk,'reject')
        with self.assertRaises(IntegrityError),transaction.atomic():
            ClinicalContribution.objects.filter(pk=item.pk).update(state='pending',reviewed_by=None,reviewed_at=None)
