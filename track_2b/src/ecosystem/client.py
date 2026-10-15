"""Real Keycloak code flow and normal CSRF-protected HTTP application contracts.

This is a protocol integration client, not a replacement authentication backend.
Passwords/cookies/tokens never enter result files or console output.
"""
import json
import secrets
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
import requests
from . import environment as env
from .prepare import VERSION


class Form(HTMLParser):
    def __init__(self): super().__init__();self.action=None;self.hidden={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form' and attrs.get('id')=='kc-form-login': self.action=attrs.get('action')
        if tag=='input' and attrs.get('type')=='hidden' and attrs.get('name'): self.hidden[attrs['name']]=attrs.get('value','')


def loopback_login_cookies(session):
    """Emulate a browser's trustworthy-loopback cookie handling in requests.

    Keycloak emits Secure cookies even for this local HTTP development origin.
    requests lacks browsers' loopback exception. This adapter is restricted to
    the dedicated loopback realm; it does not alter server settings or app cookies.
    """
    if env.KEYCLOAK!='http://127.0.0.1:8091':
        raise ValueError('Cookie adapter is restricted to isolated loopback evaluation')
    for cookie in session.cookies:
        if (cookie.name in {'AUTH_SESSION_ID','KC_AUTH_SESSION_HASH','KC_RESTART'}
            and cookie.domain=='127.0.0.1' and cookie.path=='/realms/continuity/'):
            cookie.secure=False


def provision(identities):
    config=env.credentials();session=requests.Session()
    response=session.post(env.KEYCLOAK+'/realms/master/protocol/openid-connect/token',data={
      'client_id':'admin-cli','grant_type':'password','username':'demo-admin','password':config['KEYCLOAK_ADMIN_PASSWORD']},timeout=30)
    if response.status_code!=200: raise ValueError('Synthetic Keycloak administrator authentication failed')
    session.headers['Authorization']='Bearer '+response.json()['access_token']
    known=env.accounts()
    for identity in identities:
        key=identity['id'];username=identity['account']
        response=session.get(env.KEYCLOAK+'/admin/realms/continuity/users',params={'username':username,'exact':'true'},timeout=30)
        if response.status_code!=200: raise ValueError('Synthetic user lookup failed')
        rows=response.json()
        if rows:
            # Keycloak's managed user profile can discard unmanaged attributes.
            # Ownership therefore requires the exact subject returned on creation,
            # not a match on an email, display name, or optional custom attribute.
            entry=known.get(key,{})
            if (len(rows)!=1 or entry.get('username')!=username
                or entry.get('keycloak_subject')!=rows[0]['id']):
                raise ValueError('Existing identity is not owned by this fixture; no change made')
        else:
            # Save generated credentials before provisioning: a lost HTTP response can
            # then resume via the exact fixture attribute, without resetting a password.
            entry=known.setdefault(key,{'username':username,'password':secrets.token_urlsafe(24)})
            env.save_accounts(known)
            response=session.post(env.KEYCLOAK+'/admin/realms/continuity/users',json={
              'username':username,'enabled':True,'email':username+'@example.invalid','emailVerified':False,
              'firstName':'Synthetic','lastName':key,'requiredActions':[],
              'attributes':{'comfort_fixture':[VERSION+':'+key]},
              'credentials':[{'type':'password','value':entry['password'],'temporary':False}]},timeout=30)
            if response.status_code!=201: raise ValueError('Synthetic user provisioning failed')
            subject=response.headers.get('Location','').rstrip('/').rsplit('/',1)[-1]
            if not re.fullmatch(r'[0-9a-fA-F-]{36}',subject):
                raise ValueError('Keycloak creation did not return a stable subject; inspect the isolated realm')
            entry['keycloak_subject']=subject;env.save_accounts(known)
            rows=session.get(env.KEYCLOAK+'/admin/realms/continuity/users',params={'username':username,'exact':'true'},timeout=30).json()
        known[key]['keycloak_subject']=rows[0]['id'];env.save_accounts(known)
    session.close()
    return known


class Client:
    def __init__(self,account):
        self.http=requests.Session();self.http.headers.update({'Origin':env.APP,'Referer':env.APP+'/app/'})
        self.account=account;self.data=None
    def sign_in(self):
        previous=(self.user,self.workspace) if self.data else None
        # Use a fresh local cookie jar for an explicit fixture reauthentication.
        # Otherwise a surviving Keycloak SSO cookie can bypass its login form.
        # The normal server code flow and strict origin checks remain in force.
        if previous:
            self.http.close();self.http=requests.Session()
            self.http.headers.update({'Origin':env.APP,'Referer':env.APP+'/app/'})
        self.http.get(env.APP+'/app/',timeout=30)
        csrf=self.http.cookies.get('csrftoken')
        if not csrf: raise ValueError('Normal CSRF initialization failed')
        result=self.http.post(env.APP+'/auth/login/',data={'csrfmiddlewaretoken':csrf},timeout=30)
        if urlsplit(result.url).netloc!=urlsplit(env.KEYCLOAK).netloc: raise ValueError('Unexpected OIDC authorization origin')
        form=Form();form.feed(result.text)
        if not form.action or urlsplit(form.action).netloc!=urlsplit(env.KEYCLOAK).netloc: raise ValueError('Unsupported Keycloak login step')
        loopback_login_cookies(self.http)
        result=self.http.post(form.action,data={**form.hidden,'username':self.account['username'],'password':self.account['password']},
            headers={'Origin':env.KEYCLOAK,'Referer':result.url},timeout=30)
        if urlsplit(result.url).netloc!=urlsplit(env.APP).netloc:
            title=re.search(r'<h1[^>]*id="kc-page-title"[^>]*>(.*?)</h1>',result.text,re.S)
            label=re.sub('<[^>]+>','',title.group(1)).strip()[:100] if title else 'unsupported authentication step'
            raise ValueError('OIDC callback did not complete: '+label)
        result=self.http.get(env.APP+'/api/session/',timeout=30)
        if result.status_code!=200: raise ValueError('Application rejected the verified OIDC session')
        self.data=result.json()
        if len(self.data['contexts'])!=1 or self.data['contexts'][0]['capacity']!='Self': raise ValueError('Unexpected synthetic identity context')
        self.workspace=self.data['contexts'][0]['workspace_id'];self.user=self.data['actor']['id']
        if previous and previous!=(self.user,self.workspace):raise ValueError('Reauthenticated fixture identity changed')
        return self
    def call(self,path,method='GET',data=None,files=None,expected=(200,),raw=False):
        if not path.startswith('/api/') or path.startswith('//'): raise ValueError('Only existing same-origin API contracts are allowed')
        if self.data and self.data['expires_at']<__import__('time').time()+15: self.sign_in()
        headers={'X-CSRFToken':self.http.cookies.get('csrftoken','')}
        result=self.http.request(method,env.APP+path,json=data if files is None else None,
            files=files,data=data if files else None,headers=headers,timeout=45)
        if result.status_code not in expected: raise ValueError(f'HTTP contract returned {result.status_code}; expected {expected}')
        return result if raw else result.json()
    def own(self,suffix,**kwargs): return self.call(f'/api/workspaces/{self.workspace}/'+suffix,**kwargs)
    def close(self): self.http.close()
