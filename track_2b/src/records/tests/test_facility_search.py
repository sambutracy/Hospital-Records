from datetime import timedelta
import json
import time
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from identity.models import AccessCapability, PatientWorkspace
from identity.services import resolve_verified_identity
from records.facilities import read_selection, selection_token
from records import facility_search, services
from records.models import FacilitySearchCache, FacilitySearchGate

ITEM={'name':'Example Hospital','display_name':'Example Hospital, Example Town','lat':'-1.2','lon':'36.8',
    'category':'amenity','type':'hospital','osm_type':'way','osm_id':123}


class FacilitySearchTests(TestCase):
    def setUp(self):
        self.user=resolve_verified_identity('https://facility.example.invalid','test-user','Facility test')
        self.workspace=PatientWorkspace.objects.get(subject_patient__person=self.user.person)
        self.client.force_login(self.user,backend='identity.backends.OIDCSessionBackend')
        session=self.client.session; session['oidc_expires_at']=int(time.time())+300; session.save()
        self.base=f'/api/workspaces/{self.workspace.pk}/'

    def request(self,query='Example Hospital, Example Town'):
        return self.client.post(self.base+'facilities/search/',data=json.dumps({'query':query}),content_type='application/json')

    def test_results_are_bounded_healthcare_places_with_coordinate_pins(self):
        results=facility_search.normalize_results([ITEM,{**ITEM,'osm_id':124,'type':'restaurant'},{**ITEM,'lat':'NaN'},ITEM,{**ITEM,'osm_id':125,'lat':'91'}])
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['name'],'Example Hospital')
        self.assertIn('query=-1.2%2C36.8',results[0]['maps_url'])
        self.assertEqual(results[0]['source_id'],'way/123')

    def test_search_cache_and_global_rate_gate(self):
        places=facility_search.normalize_results([ITEM])
        with patch('records.facility_search.fetch_results',return_value=places) as fetch:
            self.assertEqual(self.request().status_code,200)
            self.assertEqual(self.request().status_code,200)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(self.request('Another Hospital').status_code,429)
        self.assertEqual(FacilitySearchCache.objects.count(),1)

    def test_provider_failures_still_rate_limit_and_do_not_leak_body(self):
        with patch('records.facility_search.fetch_results',side_effect=facility_search.SearchUnavailable('private provider body')):
            first=self.request()
            self.assertEqual(first.status_code,503)
            self.assertNotIn('private provider body',first.content.decode())
            self.assertEqual(self.request('Another Hospital').status_code,429)

    def test_selection_signature_actor_scope_tampering_and_expiry(self):
        place=facility_search.normalize_results([ITEM])[0]
        token=selection_token(place,self.user,self.workspace.pk)
        self.assertEqual(read_selection(token,self.user,self.workspace.pk),place)
        with self.assertRaises(ValueError):
            read_selection(token+'tampered',self.user,self.workspace.pk)
        other=resolve_verified_identity('https://facility.example.invalid','other','Other')
        with self.assertRaises(ValueError):
            read_selection(token,other,self.workspace.pk)
        with patch('django.core.signing.time.time',return_value=time.time()+1000),self.assertRaises(ValueError):
            read_selection(token,self.user,self.workspace.pk)

    def test_authentication_csrf_revocation_and_bounded_inputs_precede_provider(self):
        from django.test import Client
        with patch('records.facility_search.fetch_results') as fetch:
            self.assertEqual(self.request('x').status_code,400)
            self.assertEqual(self.request('x'*181).status_code,400)
            anonymous=Client()
            self.assertEqual(anonymous.post(self.base+'facilities/search/',data='{}',content_type='application/json').status_code,401)
            secure=Client(enforce_csrf_checks=True)
            secure.force_login(self.user,backend='identity.backends.OIDCSessionBackend')
            self.assertEqual(secure.post(self.base+'facilities/search/',data='{}',content_type='application/json').status_code,403)
            AccessCapability.objects.filter(membership__user=self.user,rule__capability_key='read_workspace_records').update(revoked_at=timezone.now())
            self.assertEqual(self.request().status_code,404)
            fetch.assert_not_called()

    def test_revocation_during_lookup_blocks_results_and_selection_tokens(self):
        def revoke(*args):
            AccessCapability.objects.filter(membership__user=self.user,rule__capability_key='review_metadata').update(revoked_at=timezone.now())
            return facility_search.normalize_results([ITEM])
        with patch('records.facility_search.fetch_results',side_effect=revoke):
            self.assertEqual(self.request().status_code,404)
