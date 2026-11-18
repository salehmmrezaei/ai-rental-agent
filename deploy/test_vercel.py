"""Offline routing/package invariants; no Vercel or Neon credentials required."""
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VercelTests(unittest.TestCase):
    def test_same_origin_routes_api_before_frontend(self):
        config = json.loads((ROOT/'vercel.json').read_text())
        self.assertEqual(config['rewrites'][0], {'source':'/api/(.*)', 'destination':{'service':'backend'}})
        self.assertEqual(config['rewrites'][1]['destination'], {'service':'frontend'})
        service = config['services']['frontend']
        self.assertEqual(service['routes'][0], {'handle':'filesystem'})
        self.assertEqual(service['routes'][1]['dest'], '/index.html')
        self.assertEqual(config['services']['backend']['entrypoint'], 'vercel_entry:app')

    def test_runtime_dependencies_exclude_live_model_and_seed(self):
        project = tomllib.loads((ROOT/'backend/pyproject.toml').read_text())['project']
        self.assertFalse(any('openai' in d.lower() or 'faker' in d.lower() for d in project['dependencies']))
        self.assertTrue(any('openai' in d for d in project['optional-dependencies']['live']))

    def test_secrets_and_local_storage_excluded(self):
        ignore = (ROOT/'.vercelignore').read_text().splitlines()
        for pattern in ['.env','**/.env.*','backend/uploads','**/.venv','**/node_modules']:
            self.assertIn(pattern, ignore)
        config = json.loads((ROOT/'vercel.json').read_text())
        self.assertNotIn('env', config)
        self.assertNotIn('crons', config)

    def test_domain_tables_are_not_writable_by_runtime_role(self):
        grants = (ROOT/'deploy/neon-runtime-role.sql').read_text()
        self.assertIn('GRANT INSERT, UPDATE, DELETE ON demo_visitors, demo_rate_buckets', grants)
        self.assertNotIn('GRANT ALL', grants)
        self.assertNotIn('PASSWORD ', grants)


if __name__ == '__main__':
    unittest.main()
