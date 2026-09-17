"""Create one short-lived invitation; never email it automatically.

Run in backend: .venv/bin/python -m app.invite customer@example.com --output /secure/path/invitation.txt
"""
import argparse
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .db import Session
from .auth_models import Invitation
from .routers.auth import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if "@" not in email or len(email) > 250 or any(c.isspace() for c in email):
        parser.error("Enter a valid email address.")
    token = secrets.token_urlsafe(32)
    path = Path(args.output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never replace an existing secret or write through a symlink.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with Session() as db:
            db.add(Invitation(email=email, token_hash=digest(token),
                              expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
            db.commit()
        with os.fdopen(fd, "w") as output:
            output.write(f"Email: {email}\nInvitation code (expires in 7 days): {token}\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    print(f"Invitation written to {path}. Deliver it privately to the invited customer.")


if __name__ == "__main__":
    main()
