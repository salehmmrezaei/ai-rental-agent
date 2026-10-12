"""Host-side Phase 6 verification: python -m app.verify.

Requires Docker, the local backend virtualenv, frontend npm dependencies and Chrome.
Credentials stay in process environments; only disposable *_test data is truncated.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from sqlalchemy import URL

BACKEND_DATABASE = "rental_phase6_test"
BROWSER_DATABASE = "rental_browser_test"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend/frontend tests and Chrome journeys against Docker PostgreSQL")
    parser.add_argument("--skip-build", action="store_true", help="Reuse existing Docker images")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    python = root / "backend/.venv/bin/python"
    if not python.exists() or not (root / "frontend/package.json").exists():
        print("Run this command from the source checkout's backend virtualenv", file=sys.stderr)
        return 1
    local = {key: value for key, value in dotenv_values(root / ".env").items() if value is not None}
    env = local | os.environ.copy()
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "JWT_SECRET")
    if any(not env.get(key) for key in required):
        print("Configure PostgreSQL and JWT_SECRET in ignored .env first", file=sys.stderr)
        return 1
    compose = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.verify.yml"]

    def run(command, *, directory=root, extra=None):
        subprocess.run([str(value) for value in command], cwd=directory,
                       env=env | (extra or {}), check=True)

    def database_url(name):
        return URL.create("postgresql+psycopg", username=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"], host="127.0.0.1", port=5432,
            database=name).render_as_string(hide_password=False)

    try:
        run(compose + ["config", "--quiet"])
        run(compose + ["up", "-d", "--wait", "db"])
        # Names are fixed, reserved for disposable verification, and safely quoted.
        with psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres",
            user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"], autocommit=True) as connection:
            for name in (BACKEND_DATABASE, BROWSER_DATABASE):
                if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                    connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        command = compose + ["up", "-d", "--wait", "--wait-timeout", "180"]
        if not args.skip_build:
            command.append("--build")
        run(command + ["frontend", "verify-frontend"])
        test_env = {"DATABASE_URL": database_url(BACKEND_DATABASE),
                    "TEST_DATABASE_URL": database_url(BACKEND_DATABASE)}
        run([python.parent / "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], extra=test_env)
        run([python.parent / "pytest", "backend/tests", "-q"], extra=test_env)
        for command in (["npm", "run", "build"], ["npm", "test"], ["npm", "run", "lint"]):
            run(command, directory=root / "frontend")
        # Password is local to the test environment; main dev credentials stay separate.
        # Preserve it for reruns of the already-seeded disposable browser database.
        password_file = root / "frontend/.env.e2e.local"
        if password_file.exists():
            password = dotenv_values(password_file).get("E2E_DEMO_PASSWORD")
            if not password or not 12 <= len(password) <= 128:
                raise ValueError("Invalid E2E_DEMO_PASSWORD in frontend/.env.e2e.local")
        else:
            password = secrets.token_urlsafe(24)
            descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as file:
                file.write(f"E2E_DEMO_PASSWORD={password}\n")
        run(["npm", "run", "test:e2e"], directory=root / "frontend", extra={
            "E2E_DATABASE_URL": database_url(BROWSER_DATABASE), "E2E_BASE_URL": "http://127.0.0.1:5174",
            "E2E_SEED_DEMO": "1", "E2E_DEMO_PASSWORD": password})
    except (subprocess.CalledProcessError, psycopg.Error, ValueError) as exc:
        # Database errors can include connection details: keep credentials out of output.
        print("Phase 6 verification failed; inspect the failed check above and local configuration", file=sys.stderr)
        return exc.returncode if isinstance(exc, subprocess.CalledProcessError) else 1
    print("Phase 6 verification passed. Development: http://localhost:5173")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
