"""Private operator command; reads a direct owner URL without shell interpolation."""
import argparse
from getpass import getpass
from pathlib import Path
import sys
from dotenv import dotenv_values
import psycopg
from psycopg import sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--set-password', action='store_true')
    args = parser.parse_args()
    if args.env_file.stat().st_mode & 0o077:
        parser.error('Protect the operator env file with chmod 600')
    values = dotenv_values(args.env_file)
    url = values.get('DATABASE_DIRECT_URL') or values.get('DATABASE_URL')
    if not url:
        parser.error('Set a direct owner DATABASE_URL in the private operator file')
    # libpq accepts postgresql://, not SQLAlchemy's driver-qualified prefix.
    url = url.replace('postgresql+psycopg://','postgresql://',1)
    password = None
    if args.set_password:
        password = getpass('New private casa_runtime password (32+ characters): ')
        if len(password) < 32 or password != getpass('Repeat password: '):
            parser.error('Passwords must match and contain at least 32 characters')
    try:
        with psycopg.connect(url) as db:
            db.execute(Path(__file__).with_name('neon-runtime-role.sql').read_text())
            if password:
                db.execute(sql.SQL('ALTER ROLE casa_runtime PASSWORD {}').format(sql.Literal(password)))
    except psycopg.Error:
        print('Runtime role setup failed; check owner access and completed migrations privately.',file=sys.stderr)
        return 1
    print('Runtime role grants applied. Credentials were not printed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
