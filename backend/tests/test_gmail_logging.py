import logging

import pytest

from app.services.auth_logging import AuthQueryRedaction


@pytest.mark.parametrize("path,expected", [
    ("/api/mailboxes/callback?code=private-code&state=private-state", "/api/mailboxes/callback"),
    ("/api/mail/unsubscribe/private-recipient.private-signature?foo=bar", "/api/mail/unsubscribe/[redacted]"),
    ("/api/mail/unsubscribe%2Fprivate-recipient.private-signature", "/api/mail/unsubscribe/[redacted]"),
])
def test_gmail_access_logs_remove_codes_and_unsubscribe_bearer_tokens(path, expected):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:1", "GET", path, "1.1", 200), None)
    AuthQueryRedaction().filter(record)
    assert record.args[2] == expected
    assert "private-" not in record.getMessage()
