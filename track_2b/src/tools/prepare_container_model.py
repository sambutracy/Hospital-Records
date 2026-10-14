"""Prepare verified local weights/key without changing existing application secrets."""
import os
from pathlib import Path
import runpy
import secrets

runpy.run_path(str(Path(__file__).with_name('download_local_model.py')), run_name='__main__')
folder = Path(__file__).resolve().parents[2] / '.runtime' / 'local-model'
key = folder / 'server.key'
if not key.exists():
    with key.open('x', encoding='utf-8') as output:
        output.write(secrets.token_hex(32) + '\n')
value = key.read_text(encoding='utf-8').strip()
if not value or len(value) > 512 or any(c in value for c in '\r\n'):
    raise SystemExit('Invalid existing inference key; it was not replaced.')
# Windows-written CRLF otherwise becomes part of a Linux server's key line.
# Preserve the key value, normalize only the line terminator.
key.write_bytes((value + '\n').encode('utf-8'))
key.chmod(0o600)
header = folder / 'auth-header.txt'
header.write_bytes(('Authorization: Bearer ' + value + '\n').encode('utf-8'))
header.chmod(0o600)
if hasattr(os, 'geteuid') and os.geteuid() == 0:
    # The model, app and worker run as UID 10001, even on native Linux hosts.
    os.chown(key, 10001, 10001)
    os.chown(header, 10001, 10001)
print('Verified model and private inference key ready; application secrets retained.')
