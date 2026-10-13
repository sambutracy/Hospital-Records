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
        if json.loads((runtime / 'continuity-realm.json').read_text(encoding='utf-8'))['clients'][0].get('secret') != values['OIDC_CLIENT_SECRET']:
            raise SystemExit('Client secret differs between .env and demo realm. Recover matching files; no files were replaced.')
        print('Existing local demo configuration retained.')
        return
    if runtime.exists() and any(runtime.iterdir()):
        raise SystemExit('Existing runtime data found without .env. Recover the matching .env; no files were replaced.')
    values = {key: secrets.token_hex(32) for key in REQUIRED}
    realm = json.loads((root / 'src' / 'keycloak' / 'realm.template.json').read_text(encoding='utf-8'))
    realm['clients'][0]['secret'] = values['OIDC_CLIENT_SECRET']
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
