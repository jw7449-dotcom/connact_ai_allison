"""Provision the reserved administrator account from a server-side password hash."""

import re
from sqlalchemy import select
from .config import settings
from .db import Session
from .auth_models import User
from .models import Workspace


def bootstrap_admin():
    password_hash = settings.bootstrap_admin_password_hash
    if not password_hash:
        return
    if not re.fullmatch(r"[a-f0-9]{32}:[a-f0-9]{128}", password_hash):
        raise RuntimeError("Invalid administrator password hash configuration.")
    with Session() as db:
        existing = db.scalar(select(User).where(User.email == "admin"))
        if existing:
            if not existing.is_admin:
                raise RuntimeError("Reserved administrator account is already occupied.")
            return
        workspace = Workspace(name="Administrator workspace")
        db.add(workspace)
        db.flush()
        db.add(User(email="admin", password_hash=password_hash, workspace_id=workspace.id, is_admin=True))
        db.commit()
    print("Administrator account is ready.")


if __name__ == "__main__":
    bootstrap_admin()
