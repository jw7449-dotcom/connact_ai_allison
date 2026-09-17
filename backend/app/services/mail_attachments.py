"""Explicit user-selected outgoing attachments, frozen with the reviewed send.

No URL/file-path loading. MIME types are derived locally and potentially active
formats remain ordinary downloadable attachments, never rendered by the app.
"""
import base64
import binascii
import mimetypes
import unicodedata

from fastapi import HTTPException

MAX_FILES = 5
MAX_BYTES = 8 * 1024 * 1024
MAX_MIME_BYTES = 12 * 1024 * 1024


def freeze_attachments(items):
    if not isinstance(items, list) or len(items) > MAX_FILES:
        raise HTTPException(422, "Choose at most five attachments.")
    result, total = [], 0
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(422, "Invalid attachment.")
        filename = item.get("filename")
        encoded = item.get("content_base64")
        if (not isinstance(filename, str) or not filename.strip() or len(filename) > 200
            or any(unicodedata.category(c).startswith("C") for c in filename)
            or any(c in filename for c in ("/", "\\")) or filename in (".", "..")):
            raise HTTPException(422, "Use an attachment filename without paths or control characters (up to 200 characters).")
        if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES * 4 // 3) + 8:
            raise HTTPException(413, "Attachments must total at most 8 MiB before encoding.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, "Attachment content is not valid base64.") from exc
        total += len(data)
        if total > MAX_BYTES:
            raise HTTPException(413, "Attachments must total at most 8 MiB before encoding.")
        if not data:
            raise HTTPException(422, "Empty attachments cannot be sent.")
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        result.append({"filename": filename, "content_base64": base64.b64encode(data).decode(),
                       "mime_type": mime, "size": len(data)})
    return result


def attach_to_message(message, items):
    # Revalidate persisted snapshots before creating provider MIME.
    for item in freeze_attachments(items or []):
        main, sub = item["mime_type"].split("/", 1)
        message.add_attachment(base64.b64decode(item["content_base64"]),
                               maintype=main, subtype=sub, filename=item["filename"])
    if len(message.as_bytes()) > MAX_MIME_BYTES:
        raise HTTPException(413, "The encoded email exceeds the platform's 12 MiB limit.")
