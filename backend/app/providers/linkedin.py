import re
from urllib.parse import urlsplit, unquote, quote


def linkedin_profile(value):
    """Canonical public person URL; reject company pages and lookalike hosts."""
    if not isinstance(value, str):
        return ""
    try:
        url = urlsplit(value if "://" in value else "https://" + value)
        host = (url.hostname or "").lower()
        if url.scheme not in ("http", "https") or not (
            host == "linkedin.com" or host.endswith(".linkedin.com")
        ):
            return ""
        match = re.fullmatch(r"/in/([^/]+)/?", unquote(url.path))
        if not match or not re.fullmatch(r"[\w-]+", match[1]):
            return ""
        return "https://www.linkedin.com/in/" + quote(match[1].lower())
    except ValueError:
        return ""
