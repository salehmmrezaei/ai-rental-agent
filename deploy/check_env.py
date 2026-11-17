#!/usr/bin/env python3
"""Validate the restricted production env format without printing secret values."""
from pathlib import Path
import argparse
import re
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent.parent / ".env.production")
    path = parser.parse_args().env_file
    if not path.is_file():
        print("Copy .env.production.example to .env.production and configure it.", file=sys.stderr)
        return 1
    values = {}
    errors = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append("Use plain KEY=value lines in .env.production")
            continue
        key, value = line.split("=", 1)
        if key in values:
            errors.append(f"Duplicate setting: {key}")
        values[key] = value
    for key in ("POSTGRES_USER", "POSTGRES_DB", "APP_DB_USER"):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", values.get(key, "")):
            errors.append(f"{key} must be an unquoted PostgreSQL identifier")
    if values.get("APP_DB_USER") == values.get("POSTGRES_USER"):
        errors.append("APP_DB_USER must differ from the bootstrap POSTGRES_USER")
    secrets = [values.get(key, "") for key in (
        "POSTGRES_PASSWORD", "APP_DB_PASSWORD", "JWT_SECRET", "DEMO_PASSWORD")]
    for key, secret in zip(("POSTGRES_PASSWORD", "APP_DB_PASSWORD", "JWT_SECRET", "DEMO_PASSWORD"), secrets):
        if not re.fullmatch(r"[a-fA-F0-9]{64,128}", secret):
            errors.append(f"{key} must be a separately generated 64–128 character hex secret")
    if len(set(secrets)) != len(secrets):
        errors.append("Generate four different secrets")
    domain = values.get("CASA_DOMAIN", "")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        errors.append("CASA_DOMAIN must be a lowercase public hostname, without a URL scheme")
    email = values.get("ACME_EMAIL", "")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or "replace-" in email:
        errors.append("Set ACME_EMAIL to your real certificate contact email")
    if values.get("PUBLIC_DEMO_MODE") != "true":
        errors.append("PUBLIC_DEMO_MODE must be true")
    if values.get("OPENAI_API_KEY", "") or values.get("ASSISTANT_ENABLED") != "false":
        errors.append("Production requires an empty OPENAI_API_KEY and ASSISTANT_ENABLED=false")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", values.get("CASA_VERSION", "local")):
        errors.append("CASA_VERSION must be a valid image tag, such as a short commit SHA")
    for key, default, low, high in (
        ("DEMO_SESSION_MINUTES", "30", 5, 60),
        ("DEMO_MAX_SESSIONS", "1000", 10, 5000),
        ("DEMO_ACCESS_RATE_LIMIT", "20", 1, 1000),
        ("DEMO_REQUEST_RATE_LIMIT", "240", 30, 5000),
        ("DEMO_GLOBAL_RATE_LIMIT", "1200", 60, 20000),
        ("ASSISTANT_RATE_LIMIT", "10", 1, 100),
    ):
        value = values.get(key, default)
        if not value.isdigit() or not low <= int(value) <= high:
            errors.append(f"{key} must be an integer from {low} to {high}")
    if errors:
        print("Production configuration needs attention:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if path.stat().st_mode & 0o077:
        print("Set private file permissions: chmod 600 .env.production", file=sys.stderr)
        return 1
    print("Production environment passed preflight; secret values were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
