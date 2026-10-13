"""One-shot migration service. The web service never receives these credentials."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'continuity.settings')
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from identity.db_roles import configure_runtime_permissions

call_command('migrate', interactive=False)
configure_runtime_permissions(connection)
