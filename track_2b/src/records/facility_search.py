"""Explicit, cached hospital lookups against a configurable Nominatim service."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import FacilitySearchCache, FacilitySearchGate

ATTRIBUTION={'label':'© OpenStreetMap contributors','url':'https://www.openstreetmap.org/copyright','license':'ODbL-1.0'}
TYPES={'hospital','clinic','doctors','dentist','pharmacy','laboratory','health_post','health_centre','health_center'}


class SearchUnavailable(Exception):
    pass


class SearchBusy(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):
        raise SearchUnavailable()


def normalize_results(items):
    if not isinstance(items,list):
        raise SearchUnavailable()
    results=[]
    seen=set()
    for item in items[:10]:
        try:
            if item.get('type') not in TYPES and item.get('category')!='healthcare':
                continue
            name=item['name'].strip()
            address=item['display_name'].strip()
            if not name or len(name)>180 or not address or len(address)>1000:
                continue
            if len(str(item['lat']))>32 or len(str(item['lon']))>32:
                continue
            lat,lon=Decimal(item['lat']),Decimal(item['lon'])
            if not lat.is_finite() or not lon.is_finite() or not -90<=lat<=90 or not -180<=lon<=180:
                continue
            osm_type=item['osm_type']
            osm_id=item['osm_id']
            if osm_type not in ('node','way','relation') or type(osm_id) is not int or osm_id<=0:
                continue
            source=f'{osm_type}/{osm_id}'
            if source in seen:
                continue
            seen.add(source)
            coordinates=f'{lat},{lon}'
            results.append({'name':name,'address':address,'latitude':str(lat),'longitude':str(lon),
                'maps_url':'https://www.google.com/maps/search/?'+urlencode({'api':'1','query':coordinates}),
                'provider':'openstreetmap','source_id':source,'source_url':f'https://www.openstreetmap.org/{source}',
                'attribution':ATTRIBUTION})
        except (AttributeError,KeyError,TypeError,ValueError,InvalidOperation):
            continue
    return results


def fetch_results(query,endpoint):
    parameters=urlencode({'q':query,'format':'jsonv2','limit':10,'layer':'poi','accept-language':'en'})
    request=Request(endpoint+'/search?'+parameters,headers={'User-Agent':'Comfort/0.1 (https://github.com/sambutracy/Hospital-Records)', 'Accept':'application/json'})
    try:
        with build_opener(NoRedirect()).open(request,timeout=6) as response:
            data=response.read(262145)
        if len(data)>262144:
            raise SearchUnavailable()
        return normalize_results(json.loads(data))
    except Exception:
        raise SearchUnavailable() from None


def search(query):
    if not isinstance(query,str):
        raise ValueError('Enter a hospital name and town.')
    query=' '.join(query.split())
    if not 3<=len(query)<=180 or any(ord(c)<32 for c in query):
        raise ValueError('Enter a hospital name and town.')
    endpoint=settings.FACILITY_SEARCH_URL.rstrip('/')
    parts=urlsplit(endpoint)
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or (parts.scheme!='https' and not (parts.scheme=='http' and parts.hostname in ('localhost','127.0.0.1','facility-search','host.docker.internal'))):
        raise SearchUnavailable()
    key=hashlib.sha256((endpoint+'\n'+query.casefold()).encode()).hexdigest()
    cached=FacilitySearchCache.objects.filter(pk=key,expires_at__gt=timezone.now()).first()
    if cached:
        return cached.results
    failed=False
    with transaction.atomic():
        FacilitySearchGate.objects.get_or_create(pk=1,defaults={'next_allowed_at':timezone.now()})
        gate=FacilitySearchGate.objects.select_for_update().get(pk=1)
        cached=FacilitySearchCache.objects.filter(pk=key,expires_at__gt=timezone.now()).first()
        if cached:
            return cached.results
        now=timezone.now()
        if gate.next_allowed_at>now:
            raise SearchBusy()
        gate.next_allowed_at=now+timedelta(seconds=1.1)
        gate.save(update_fields=['next_allowed_at'])
        try:
            results=fetch_results(query,endpoint)
            FacilitySearchCache.objects.update_or_create(pk=key,defaults={'results':results,'expires_at':now+timedelta(days=7)})
        except SearchUnavailable:
            # Commit the rate gate even on provider failure; never log its response body.
            failed=True
    if failed:
        raise SearchUnavailable()
    return results
