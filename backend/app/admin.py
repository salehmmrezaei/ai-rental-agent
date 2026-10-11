"""Local operator command: python -m app.admin --email ... --full-name ..."""
import argparse
from getpass import getpass
import sys
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_engine
from app.errors import ApiError
from app.schemas.auth import Register
from app.services.auth import provision_admin


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision an agency administrator locally")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()
    try:
        password = getpass("Administrator password (12–128 characters): ")
        if password != getpass("Confirm password: "):
            print("Passwords do not match", file=sys.stderr)
            return 1
        data = Register(email=args.email, full_name=args.full_name, password=password)
        with Session(get_engine()) as session:
            provision_admin(session, data)
    except ValidationError:
        print("Invalid email, name or password length", file=sys.stderr)
        return 1
    except ApiError as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Database operation unavailable", file=sys.stderr)
        return 1
    print("Administrator created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
