"""Patient-selected Google Maps links; never resolved or inferred by the server."""
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from django.core import signing

MAPS_URL_PATTERN = r'^https://((www\.)?google\.com/maps(/|\?|$)|maps\.google\.com(/|\?|$)|maps\.app\.goo\.gl/[A-Za-z0-9_-]+(/|\?|$)|goo\.gl/maps/[A-Za-z0-9_-]+(/|\?|$))'


def validate_maps_url(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('Provide a Google Maps share link.')
    value = value.strip()
    if not value or len(value)>2048 or '\\' in value or any(character.isspace() for character in value):
        raise ValueError('Invalid Google Maps link.')
    if any(ord(character)<32 or ord(character)==127 for character in unquote(value)):
        raise ValueError('Invalid Google Maps link.')
    try:
        parts = urlsplit(value)
        if parts.scheme!='https' or parts.username or parts.password or parts.port is not None or not parts.hostname:
            raise ValueError('Invalid Google Maps link.')
        normalized = urlunsplit(('https',parts.hostname.lower(),parts.path,parts.query,parts.fragment))
    except (ValueError, UnicodeError):
        raise ValueError('Invalid Google Maps link.') from None
    if not re.match(MAPS_URL_PATTERN,normalized):
        raise ValueError('Use a Google Maps place/pin URL or its Share link.')
    return normalized


def selection_token(location,user,workspace_id):
    return signing.dumps({'location':location,'user':str(user.pk),'workspace':str(workspace_id)},salt='comfort-facility-selection-v1',compress=True)


def read_selection(token,user,workspace_id):
    if not isinstance(token,str) or len(token)>6000:
        raise ValueError('Choose a hospital from the search results.')
    try:
        selection=signing.loads(token,salt='comfort-facility-selection-v1',max_age=900)
        if selection['user']!=str(user.pk) or selection['workspace']!=str(workspace_id):
            raise ValueError('Search selection is not available.')
        return selection['location']
    except (signing.BadSignature,TypeError,KeyError):
        raise ValueError('Search again to choose the hospital.') from None
