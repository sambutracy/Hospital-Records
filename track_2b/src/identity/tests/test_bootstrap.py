import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from tools.bootstrap_demo import initialize, REQUIRED


class DemoBootstrapTests(SimpleTestCase):
    def test_generates_private_config_and_retains_it_on_repeat(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'src' / 'keycloak').mkdir(parents=True)
            shutil.copyfile(Path(__file__).resolve().parents[2] / 'keycloak' / 'realm.template.json', root / 'src' / 'keycloak' / 'realm.template.json')
            initialize(root)
            original = (root / '.env').read_bytes()
            env = dict(line.split('=', 1) for line in original.decode().splitlines() if '=' in line)
            self.assertTrue(all(len(env[key]) >= 32 for key in REQUIRED))
            realm = json.loads((root / '.runtime' / 'continuity-realm.json').read_text())
            self.assertEqual(realm['clients'][0]['secret'], env['OIDC_CLIENT_SECRET'])
            self.assertNotEqual(realm['users'][0]['credentials'][0]['value'], realm['users'][1]['credentials'][0]['value'])
            initialize(root)
            self.assertEqual((root / '.env').read_bytes(), original)

    def test_incomplete_existing_configuration_is_not_overwritten(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env').write_text('DJANGO_SECRET_KEY=example\n')
            with self.assertRaises(SystemExit):
                initialize(root)
            self.assertEqual((root / '.env').read_text(), 'DJANGO_SECRET_KEY=example\n')
