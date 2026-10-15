from unittest import skipUnless
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from identity.models import AccessCapability
from records import services, journal, medications, continuity, care_services, insights
from records.models import AssistantTask, PatientHealthConcern
from records.metadata import UNKNOWN_DATE
from . import test_backend
from .test_journal import VALUES, DRAFT


@skipUnless(connection.vendor=='postgresql','Native date projections and SQL unions')
class InsightsTests(TestCase):
    setUpTestData=classmethod(test_backend.BackendTests.setUpTestData.__func__)
    setUp=test_backend.BackendTests.setUp
    sign_in=test_backend.BackendTests.sign_in
    upload=test_backend.BackendTests.upload
    confirm=test_backend.BackendTests.confirm

    def get(self,route='timeline',query=''):
        return self.client.get(self.base+'insights/'+route+'/?from=2026-10-01&to=2026-10-31'+query)

    def symptom(self,day,severity=None,**extra):
        return journal.save(self.alice,self.workspace.pk,{**VALUES,'category':'symptom','severity':severity,
            'occurrence':{'precision':'day','year':2026,'month':10,'day':day},**extra},0)

    def test_mixed_projection_provenance_partial_dates_and_undated_episodes(self):
        symptom=self.symptom(16)
        version=self.upload()
        self.assertEqual(self.confirm(version,{**test_backend.VALUES,'document_date':{'precision':'month','year':2026,'month':10,'day':None}}).status_code,200)
        episode=continuity.create_episode(self.alice,self.workspace.pk,'Fictional recovery grouping')
        continuity.link_sources(self.alice,self.workspace.pk,episode.pk,[str(version.pk)])
        medications.save(self.alice,self.workspace.pk,{
            'medicine_name':'Fictional medicine','dose':'As recorded','frequency':'Unknown','route':'','instructions':'',
            'use_status':'reported_prescribed','visit_date':{'precision':'year','year':2026,'month':None,'day':None},
            'episode_id':str(episode.pk),'source_version_id':str(version.pk)},0)
        response=self.get();self.assertEqual(response.status_code,200,response.content)
        rows=response.json()['items'];self.assertEqual({r['kind'] for r in rows},{'journal','document','medication'})
        doc=next(r for r in rows if r['kind']=='document');self.assertIsNone(doc['occurrence']['day'])
        self.assertIn('not clinical verification',doc['review_status'])
        med=next(r for r in rows if r['kind']=='medication');self.assertIn('actual use not established',med['description'])
        self.assertEqual(med['occurrence']['precision'],'year');self.assertIsNone(med['occurrence']['month'])
        self.assertEqual(next(r for r in rows if r['kind']=='journal')['source_id'],str(symptom.pk))
        undated=self.get(query='&date_scope=undated').json();self.assertEqual(undated['undated_count'],1)
        self.assertEqual(undated['items'][0]['kind'],'episode');self.assertEqual(undated['items'][0]['occurrence'],UNKNOWN_DATE)

    def test_counts_and_scores_only_use_exact_active_symptom_observations(self):
        self.symptom(2,0);self.symptom(2,None);self.symptom(9,6);self.symptom(16,4)
        self.symptom(17,None,occurrence={'precision':'month','year':2026,'month':10,'day':None})
        self.symptom(17,None,occurrence=UNKNOWN_DATE)
        journal.save(self.alice,self.workspace.pk,VALUES,0)
        archived=self.symptom(4,9);journal.change_status(self.alice,self.workspace.pk,archived.pk,'archived',1)
        journal.save_draft(self.alice,self.workspace.pk,{**DRAFT,'category':'symptom'},0,None,0)
        result=self.get('observations').json()
        self.assertEqual(result['exact_dated_observations'],4);self.assertEqual(result['days_with_observations'],3)
        self.assertEqual(result['days_without_entries'],28);self.assertEqual(result['scored_observations'],3)
        self.assertEqual(result['unscored_observations'],1);self.assertTrue(result['chart_ready'])
        self.assertEqual(result['partial_date_observations_excluded'],1);self.assertEqual(result['undated_observations_excluded'],1)
        second=result['bins'][1];self.assertEqual(second['observations'],2);self.assertEqual(second['severity_min'],0)
        missing=result['bins'][2];self.assertEqual(missing['observations'],0);self.assertIsNone(missing['severity_min'])
        self.assertIsNone(missing['severity_max']);self.assertEqual(AssistantTask.objects.count(),0)

    def test_insufficient_observations_and_authorized_detail_links(self):
        symptom=self.symptom(16,5)
        result=self.get('observations').json();self.assertFalse(result['chart_ready'])
        row=self.get().json()['items'][0]
        self.assertTrue(row['href'].endswith('/journal/'+str(symptom.pk)))
        self.assertEqual(self.client.get(self.base+'journal/'+str(symptom.pk)+'/').status_code,200)

    def test_concern_filter_uses_only_explicit_links(self):
        concern=PatientHealthConcern.objects.create(workspace=self.workspace,updated_by=self.alice,title='Fictional concern')
        self.symptom(16,3,concern_id=str(concern.pk));self.symptom(17,8)
        self.upload()
        query='&concern='+str(concern.pk)
        rows=self.get(query=query).json()['items'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['concern_id'],str(concern.pk))
        result=self.get('observations',query).json();self.assertEqual(result['exact_dated_observations'],1)
        foreign=PatientHealthConcern.objects.create(workspace=self.bob_workspace,updated_by=self.bob,title='Private foreign concern')
        self.assertEqual(self.get(query='&concern='+str(foreign.pk)).status_code,404)

    def test_cross_patient_share_recipient_revocation_and_no_store(self):
        self.symptom(16,3)
        version=self.upload();packet=services.create_packet(self.alice,self.workspace.pk,'Fictional only',[str(version.pk)])
        continuity.create_grant(self.alice,self.workspace.pk,'read',packet.revisions.get().pk,self.bob.pk,'Fictional only',60)
        self.assertEqual(self.get()['Cache-Control'],'no-store, private')
        self.sign_in(self.bob)
        for route in ('timeline','observations'):self.assertEqual(self.get(route).status_code,404)
        self.sign_in(self.alice)
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_profile').update(revoked_at=timezone.now())
        self.assertEqual(self.get().status_code,404);self.assertEqual(self.get('observations').status_code,404)
        self.client.logout();self.assertEqual(self.get().status_code,401)

    def test_medication_permission_does_not_leak_through_timeline(self):
        medications.save(self.alice,self.workspace.pk,{'medicine_name':'PRIVATE-MEDICATION','dose':'','frequency':'','route':'','instructions':'',
            'use_status':'unknown','visit_date':{'precision':'day','year':2026,'month':10,'day':16},'episode_id':None,'source_version_id':None},0)
        self.assertIn('PRIVATE-MEDICATION',self.get().content.decode())
        AccessCapability.objects.filter(membership__user=self.alice,rule__capability_key='manage_medications').update(revoked_at=timezone.now())
        result=self.get();self.assertFalse(result.json()['medications_included']);self.assertNotIn('PRIVATE-MEDICATION',result.content.decode())

    def test_current_versions_and_episode_filter_never_substitute_new_versions(self):
        version=self.upload()
        episode=continuity.create_episode(self.alice,self.workspace.pk,'Fictional grouping')
        continuity.link_sources(self.alice,self.workspace.pk,episode.pk,[str(version.pk)])
        newer=self.upload('A different fictional original',version.record)
        rows=self.get(query='&date_scope=undated&kind=document').json()['items']
        self.assertEqual([row['source_version_id'] for row in rows],[str(newer.pk)])
        filtered=self.get(query=f'&date_scope=undated&episode={episode.pk}').json()['items']
        self.assertEqual([row['kind'] for row in filtered],['episode'])

    def test_pagination_is_global_stable_and_bounded_for_large_history(self):
        from django.test.utils import CaptureQueriesContext
        for index in range(103): journal.save(self.alice,self.workspace.pk,{**VALUES,'description':f'Fictional observation {index}'},0)
        all_ids=[]
        for page in range(1,5):
            result=self.get(query=f'&page={page}').json();self.assertLessEqual(len(result['items']),30)
            all_ids.extend(row['id'] for row in result['items'])
        self.assertEqual(len(all_ids),103);self.assertEqual(len(set(all_ids)),103)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(len(self.get().json()['items']),30)
        self.assertLess(len(queries),40) # Queries are batched, not one per event in history.

    def test_unknown_or_partial_dates_do_not_appear_as_exact_days(self):
        self.symptom(16,7,occurrence=UNKNOWN_DATE)
        self.symptom(16,4,occurrence={'precision':'year','year':2026,'month':None,'day':None})
        rows=self.get().json()['items'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['occurrence']['precision'],'year')
        self.assertEqual(self.get('observations').json()['exact_dated_observations'],0)
        self.assertEqual(self.get(query='&date_scope=undated').json()['items'][0]['occurrence'],UNKNOWN_DATE)

    def test_filters_are_validated_and_empty_workspace_is_truthful(self):
        result=self.get();self.assertEqual(result.status_code,200,result.content);self.assertEqual(result.json()['items'],[])
        for extra in ('&kind=diagnosis','&origin=verified','&page=-1','&document_type=made_up','&date_scope=all','&episode=bad','&secret=yes'):
            self.assertEqual(self.get(query=extra).status_code,400)
        self.assertEqual(self.client.get(self.base+'insights/timeline/?from=2020-01-01&to=2026-01-01').status_code,400)
        for suffix in ('','?from=bad&to=2026-10-16','?from=2026-10-16'):
            self.assertEqual(self.client.get(self.base+'insights/timeline/'+suffix).status_code,400)

    def test_accepted_contribution_is_not_claimed_as_verified_clinician(self):
        episode=continuity.create_episode(self.alice,self.workspace.pk,'Fictional submission')
        grant=continuity.create_grant(self.alice,self.workspace.pk,'contribute',episode.pk,self.bob.pk,'Fictional contribution',60)
        submission,_=continuity.contribute(self.bob,grant.pk,SimpleUploadedFile('fictional-contribution.pdf',test_backend.pdf('Fictional submitted original')))
        continuity.review_contribution(self.alice,self.workspace.pk,submission.pk,'accept')
        row=self.get(query='&date_scope=undated&kind=document').json()['items'][0]
        self.assertEqual(row['provenance'],'accepted_contribution');self.assertIn('unverified',row['details'][1]['value'])

    def test_care_relationship_provenance_and_runtime_role_can_read_projections(self):
        from identity.db_roles import configure_runtime_permissions
        from records.models import ShareGrant, ProviderContributionAuthority
        concern=care_services.save(self.alice,self.workspace.pk,'concerns',{
            'title':'Fictional patient-reported concern','description':'Not a diagnosis','kind':'investigation',
            'certainty':'unconfirmed','onset':{'precision':'year','year':2026,'month':None,'day':None}},0)
        practitioner=care_services.save(self.alice,self.workspace.pk,'practitioners',{
            'name':'Fictional unverified doctor','specialty':'Not supplied','facility':'Fictional clinic','notes':''},0)
        assignment=care_services.save(self.alice,self.workspace.pk,'assignments',{
            'practitioner_id':str(practitioner.pk),'concern_id':str(concern.pk),'role':'Reported treating doctor',
            'participation':'historical','start_date':{'precision':'month','year':2026,'month':10,'day':None},
            'end_date':UNKNOWN_DATE,'notes':'Patient report only'},0)
        configure_runtime_permissions(connection)
        with connection.cursor() as cursor: cursor.execute('SET LOCAL ROLE continuity_app')
        try:
            result=self.get(query='&concern='+str(concern.pk));self.assertEqual(result.status_code,200,result.content)
            row=next(r for r in result.json()['items'] if r['kind']=='care_relationship')
            self.assertEqual(row['source_id'],str(assignment.pk));self.assertIn('unverified',row['review_status'])
            self.assertIn('historical',row['description']);self.assertEqual(row['occurrence']['precision'],'month')
            self.assertEqual(self.get('observations').status_code,200)
        finally:
            with connection.cursor() as cursor: cursor.execute('RESET ROLE')
        self.assertEqual(ShareGrant.objects.count(),0);self.assertEqual(ProviderContributionAuthority.objects.count(),0)
