#!/usr/bin/env python3
"""Harden default development accounts created by seed_data.py.

Usage:
  python scripts/disable_default_users.py            # list matches only
  python scripts/disable_default_users.py --deactivate  # set is_active=False
  python scripts/disable_default_users.py --delete       # remove the users

Run this against production once after deploying with MIRAI_SEED_DEFAULT_USERS=0.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.security import verify_password  # noqa: E402

DEFAULT_CREDENTIALS = {
    "admin": "admin123",
    "reviewer": "reviewer123",
    "site": "site123",
    "viewer": "viewer123",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deactivate", action="store_true", help="deactivate matches")
    group.add_argument("--delete", action="store_true", help="delete matches")
    args = parser.parse_args()

    db = SessionLocal()
    matches = []
    for user in db.query(User).all():
        default_password = DEFAULT_CREDENTIALS.get(user.username)
        if default_password and verify_password(default_password, user.password_hash):
            matches.append(user)
    if not matches:
        print("OK: no default-credential users found")
        db.close()
        return 0

    print(f"Found {len(matches)} user(s) with default credentials:")
    for u in matches:
        print(f"  - {u.username} (role={u.role}, active={u.is_active})")

    if args.deactivate:
        for u in matches:
            u.is_active = False
        db.commit()
        print("Deactivated:", ", ".join(u.username for u in matches))
    elif args.delete:
        for u in matches:
            db.delete(u)
        db.commit()
        print("Deleted:", ", ".join(u.username for u in matches))
    else:
        print("Dry run: pass --deactivate or --delete to apply.")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
