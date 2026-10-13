"""Serve with runtime database credentials; migrations run in a separate service."""
import os
os.execvp('gunicorn', [
    'gunicorn', '--chdir', 'src', 'continuity.wsgi:application',
    '--bind', '0.0.0.0:8000', '--workers', '2', '--timeout', '30',
])
