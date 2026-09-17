"""Signed workspace-scoped opt-out links; GET never changes suppression state."""
import base64
import hashlib
import hmac
import json
from html import escape

from fastapi import HTTPException

from ..config import settings
from .gmail import cipher


def _keys():
    cipher()  # Same validated secret/rotation configuration as mailbox tokens.
    return [base64.urlsafe_b64decode(key.strip()) for key in settings.gmail_token_encryption_keys.split(",") if key.strip()]


def _mac(key, payload):
    return hmac.new(key, b"connact-mail-optout-v1:" + payload.encode(), hashlib.sha256).hexdigest()


def unsubscribe_url(workspace_id, email):
    payload = base64.urlsafe_b64encode(json.dumps({"w": workspace_id, "e": email}, separators=(",", ":")).encode()).decode().rstrip("=")
    return settings.public_origin.rstrip("/") + "/api/mail/unsubscribe/" + payload + "." + _mac(_keys()[0], payload)


def verify_token(token):
    if not isinstance(token, str) or len(token) > 1200 or token.count(".") != 1:
        raise HTTPException(404, "This unsubscribe link is invalid.")
    payload, signature = token.split(".")
    if not any(hmac.compare_digest(_mac(key, payload), signature) for key in _keys()):
        raise HTTPException(404, "This unsubscribe link is invalid.")
    try:
        record = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(record, dict) or not isinstance(record.get("w"), str) or not isinstance(record.get("e"), str):
            raise ValueError()
        return record["w"], record["e"]
    except (ValueError, UnicodeError, TypeError) as exc:
        raise HTTPException(404, "This unsubscribe link is invalid.") from exc


def append_footer(snapshot, workspace_id):
    url = unsubscribe_url(workspace_id, snapshot["recipient_email"])
    snapshot["unsubscribe_url"] = url
    snapshot["body_text"] += "\n\nTo stop emails from this sender's Connact.ai workspace: " + url
    snapshot["body_html"] += '<p><a href="' + escape(url, quote=True) + '">Stop emails from this sender</a></p>'
    return snapshot
