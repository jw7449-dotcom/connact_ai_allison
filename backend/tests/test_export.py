from email import policy
from email.parser import BytesParser


def test_export_resolves_variables_and_stays_unsent(client):
    contact = client.post("/api/contacts", json={"name": "Demo recipient", "email": "recipient@example.test"}).json()
    draft = client.post("/api/drafts", json={"contact_id": contact["id"], "subject": "Hello {{name}}", "body_html": "<p>Hello {{name}},</p><p>May we connect?</p>"}).json()
    result = client.get(f'/api/drafts/{draft["id"]}/export.eml')
    assert result.status_code == 200
    message = BytesParser(policy=policy.default).parsebytes(result.content)
    assert message["To"] == contact["email"]
    assert message["Subject"] == "Hello Demo recipient"
    assert message["X-Unsent"] == "1"
    assert "Demo recipient" in message.get_body(preferencelist=("html",)).get_content()
    assert client.get(f'/api/drafts/{draft["id"]}').json()["status"] == "draft"


def test_export_rejects_missing_variables(client):
    draft = client.post("/api/drafts", json={"subject": "Hi {{unknown}}", "body_html": "<p>Hello</p>"}).json()
    assert client.get(f'/api/drafts/{draft["id"]}/export.eml').status_code == 422
    contact = client.post("/api/contacts", json={"name": "No address yet"}).json()
    draft = client.post("/api/drafts", json={"contact_id": contact["id"], "subject": "Hello", "body_html": "<p>Hello</p>"}).json()
    assert client.get(f'/api/drafts/{draft["id"]}/export.eml').status_code == 422
