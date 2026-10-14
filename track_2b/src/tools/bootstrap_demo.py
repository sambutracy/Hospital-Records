"""Initialize a private, repeatable local demo without committing credentials."""
import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ('DJANGO_SECRET_KEY', 'DATABASE_PASSWORD', 'APP_DATABASE_PASSWORD',
            'KEYCLOAK_DATABASE_PASSWORD', 'KEYCLOAK_ADMIN_PASSWORD', 'OIDC_CLIENT_SECRET')


def initialize(root=ROOT):
    env_path = root / '.env'
    runtime = root / '.runtime'
    if env_path.exists():
        values = {}
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
        if not all(values.get(key) for key in REQUIRED) or not (runtime / 'continuity-realm.json').is_file():
            raise SystemExit('Existing .env/demo realm is incomplete. Follow src/README.md setup recovery; no files were replaced.')
        client=json.loads((runtime / 'continuity-realm.json').read_text(encoding='utf-8'))['clients'][0]
        if client.get('secret') != values['OIDC_CLIENT_SECRET']:
            raise SystemExit('Client secret differs between .env and demo realm. Recover matching files; no files were replaced.')
        port=os.environ.get('APP_PORT',values.get('APP_PORT','8000'))
        host=os.environ.get('APP_HOST',values.get('APP_HOST','localhost'))
        if client.get('redirectUris') != ['http://'+host+':'+port+'/auth/callback/']:
            raise SystemExit('Existing demo redirect origin differs from requested app port. Retain matching settings; no files were replaced.')
        print('Existing local demo configuration retained.')
        return
    if runtime.exists() and any(runtime.iterdir()):
        raise SystemExit('Existing runtime data found without .env. Recover the matching .env; no files were replaced.')
    values = {key: secrets.token_hex(32) for key in REQUIRED}
    ports={name:os.environ.get(name,default) for name,default in (('APP_PORT','8000'),('KEYCLOAK_PORT','8081'))}
    if any(not port.isdigit() or not 1024<=int(port)<=65535 for port in ports.values()):
        raise SystemExit('Demo listener ports must be integers between 1024 and 65535.')
    host=os.environ.get('APP_HOST','localhost')
    if host not in ('localhost','127.0.0.1'):
        raise SystemExit('The local demo host must be localhost or 127.0.0.1.')
    realm = json.loads((root / 'src' / 'keycloak' / 'realm.template.json').read_text(encoding='utf-8'))
    realm['clients'][0]['secret'] = values['OIDC_CLIENT_SECRET']
    origin='http://'+host+':'+ports['APP_PORT']
    realm['clients'][0]['redirectUris']=[origin+'/auth/callback/']
    realm['clients'][0]['webOrigins']=[origin]
    realm['clients'][0]['attributes']['post.logout.redirect.uris']=origin+'/auth/logged-out/'
    credentials = []
    for user in realm['users']:
        password = secrets.token_urlsafe(24)
        user['credentials'] = [{'type': 'password', 'value': password, 'temporary': False}]
        credentials.append(f"{user['username']}: {password}")
    runtime.mkdir(mode=0o700, exist_ok=True)
    realm_path = runtime / 'continuity-realm.json'
    realm_path.write_text(json.dumps(realm, indent=2) + '\n', encoding='utf-8')
    credentials_path = runtime / 'demo-credentials.txt'
    credentials_path.write_text(
        'LOCAL SYNTHETIC DEMO ONLY — keep private\n\n' + '\n'.join(credentials)
        + '\n\nKeycloak administrator: demo-admin\nAdmin password is in .env (KEYCLOAK_ADMIN_PASSWORD).\n',
        encoding='utf-8',
    )
    env_path.write_text(
        '# Generated private local demo configuration. Do not commit.\n'
        + '\n'.join(f'{key}={value}' for key, value in values.items())
        + '\n' + '\n'.join(f'{key}={value}' for key,value in ports.items())
        + '\nAPP_HOST='+host
        + '\nLLM_NAME=swiss-ai/Apertus-v1.5-8B\nLLM_BASE_URL=\nLLM_API_KEY=\n',
        encoding='utf-8',
    )
    for path in (env_path, realm_path, credentials_path):
        os.chmod(path, 0o600)
    if hasattr(os, 'chown') and os.geteuid() == 0:
        # Docker bootstrap runs as root. Host user must be able to read the
        # private credentials; Keycloak's UID 1000 must read its imported file.
        owner = root.stat()
        for path in (env_path, credentials_path, runtime):
            os.chown(path, owner.st_uid, owner.st_gid)
        os.chown(realm_path, 1000, 1000)
    print('Local demo initialized. Read .runtime/demo-credentials.txt for synthetic sign-in accounts.')


if __name__ == '__main__':
    initialize()
