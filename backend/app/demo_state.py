"""Private maintenance: python -m app.demo_state --cleanup (or --reset).

Deletes only disposable state tables, never users, rentals, images or live chats.
No public API route exposes these commands; no cron or always-on process needed.
"""
import argparse
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.database import get_engine
from app.models.demo import DemoVisitor, DemoRateBucket
from app.shared_demo import cleanup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--cleanup', action='store_true')
    group.add_argument('--reset', action='store_true')
    args = parser.parse_args()
    with Session(get_engine()) as db, db.begin():
        if args.reset:
            db.execute(delete(DemoVisitor))
            db.execute(delete(DemoRateBucket))
        else:
            cleanup(db)
    print('Disposable demo state maintenance completed; rental records unchanged.')


if __name__ == '__main__':
    main()
