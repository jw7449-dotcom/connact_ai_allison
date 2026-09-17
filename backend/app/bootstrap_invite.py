"""Idempotent first invitation for hosts without shell access. Never stores a raw token."""

import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .config import settings
from .db import Session
from .auth_models import Invitation, User


def bootstrap_invite():
    if settings.auth_mode != "invite":
        return
    email = settings.bootstrap_invite_email.strip().lower()
    token_hash = settings.bootstrap_invite_token_hash
    if not email and not token_hash:
        return
    if (
        settings.auth_mode != "invite"
        or (email and "@" not in email)
        or len(email) > 250
        or any(c.isspace() for c in email)
        or not re.fullmatch(r"[a-f0-9]{64}", token_hash)
    ):
        raise RuntimeError("Invalid bootstrap invitation configuration.")
    with Session() as db:
        if email and db.scalar(select(User.id).where(User.email == email)):
            return
        invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash).with_for_update())
        if invitation:
            # A fixed, explicitly configured date can amend an existing invitation.
            # It never resets usage or moves the deadline forward on each restart.
            expiry = settings.bootstrap_invite_expires_at
            current = invitation.expires_at
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            if (expiry is not None and expiry != current and not invitation.used_at
                    and invitation.use_count < invitation.max_uses):
                invitation.expires_at = expiry
                db.commit()
                print("Initial invitation expiry updated.")
            return
        db.add(
            Invitation(
                email=email,
                token_hash=token_hash,
                max_uses=settings.bootstrap_invite_max_uses,
                expires_at=settings.bootstrap_invite_expires_at or datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        db.commit()
    print("Initial invitation is ready. No invitation code is written to server logs.")


if __name__ == "__main__":
    bootstrap_invite()
