"""Security checks for the public-deployment configuration gate (stdlib only)."""
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest


class ProductionPreflightTests(unittest.TestCase):
    def configured(self):
        data = (Path(__file__).resolve().parent.parent / ".env.production.example").read_text()
        data = data.replace("replace-with-your-email@example.com", "operator@example.com")
        for _ in range(4):
            data = data.replace("replace-with-independent-64-character-hex-secret", secrets.token_hex(32), 1)
        return data

    def run_check(self, data, permissions=0o600):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "production.env"
            path.write_text(data)
            path.chmod(permissions)
            return subprocess.run([sys.executable, str(Path(__file__).with_name("check_env.py")), "--env-file", str(path)],
                                  capture_output=True, text=True, check=False)

    def test_valid_dedicated_configuration_is_accepted(self):
        self.assertEqual(self.run_check(self.configured()).returncode, 0)

    def test_placeholders_fail_without_echoing_passwords(self):
        data = self.configured()
        original = next(line.split("=", 1)[1] for line in data.splitlines() if line.startswith("APP_DB_PASSWORD="))
        result = self.run_check(data.replace(original, "replace-with-a-secret"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(original, result.stdout + result.stderr)
        self.assertNotIn("replace-with-a-secret", result.stdout + result.stderr)

    def test_reused_secret_and_live_llm_configuration_are_rejected(self):
        data = self.configured()
        values = dict(line.split("=", 1) for line in data.splitlines() if line and not line.startswith("#"))
        result = self.run_check(data.replace(values["DEMO_PASSWORD"], values["JWT_SECRET"]).replace("OPENAI_API_KEY=", "OPENAI_API_KEY=secret-key"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different secrets", result.stderr)
        self.assertIn("empty OPENAI_API_KEY", result.stderr)
        self.assertNotIn("secret-key", result.stderr)

    def test_public_file_permissions_are_rejected(self):
        result = self.run_check(self.configured(), 0o644)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("chmod 600", result.stderr)

    def test_limits_and_bootstrap_role_cannot_bypass_application_constraints(self):
        data = self.configured().replace("APP_DB_USER=casa_app", "APP_DB_USER=casa_bootstrap")
        data = data.replace("DEMO_REQUEST_RATE_LIMIT=240", "DEMO_REQUEST_RATE_LIMIT=5001")
        data = data.replace("DEMO_GLOBAL_RATE_LIMIT=1200", "DEMO_GLOBAL_RATE_LIMIT=59")
        result = self.run_check(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differ from", result.stderr)
        self.assertIn("30 to 5000", result.stderr)
        self.assertIn("60 to 20000", result.stderr)


if __name__ == "__main__":
    unittest.main()
