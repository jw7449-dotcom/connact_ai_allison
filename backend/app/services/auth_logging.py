"""Keep authorization codes and state out of Uvicorn's request access log."""
import logging
from urllib.parse import unquote


class AuthQueryRedaction(logging.Filter):
    def filter(self, record):
        # Uvicorn's h11 and httptools implementations share this tuple shape.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            full_path = args[2]
            if isinstance(full_path, str):
                path = full_path.split("?", 1)[0]
                if unquote(path).startswith("/api/mail/unsubscribe/"):
                    args[2] = "/api/mail/unsubscribe/[redacted]"
                    record.args = tuple(args)
                elif unquote(path).startswith(("/api/auth/", "/api/mailboxes/callback")):
                    args[2] = path
                    record.args = tuple(args)
        return True


def configure_auth_log_redaction():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, AuthQueryRedaction) for item in logger.filters):
        logger.addFilter(AuthQueryRedaction())
