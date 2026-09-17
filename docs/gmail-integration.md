# Gmail sending and contact-only Inbox

Google platform sign-in and Gmail mailbox consent are separate. A workspace can connect several Gmail accounts, including addresses different from its login email. Gmail uses the real API; missing configuration and provider failures never return simulated success.

## Configure the server

1. Enable **Gmail API** in the Google Cloud project containing the OAuth client. Keep development consent in Testing and add the mailbox owners as test users.
2. In the web application's OAuth client, retain its sign-in callback and add the mailbox callback exactly:
   - Local: `http://127.0.0.1:3100/api/mailboxes/callback`
   - Current deployment: `https://connact-ai.onrender.com/api/mailboxes/callback`
3. Keep `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the backend. To use a separate Gmail client, set both `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`; leaving both blank reuses the sign-in client. Set `PUBLIC_ORIGIN` to the frontend origin. Public deployments require HTTPS and authenticated workspaces.
4. Generate a persistent encryption key, store it as `GMAIL_TOKEN_ENCRYPTION_KEYS` in backend secrets, and keep its backup separate from database backups. Never place it in frontend environment variables, Git, handoff bundles or logs:

   ```bash
   backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   Do not replace this key on each deploy. For rotation, supply `new-key,old-key`; new credentials use the first key and existing credentials can be read with retained keys. Reconnect or migrate every credential before removing an old key.
5. Apply the migration and restart the existing stack:

   ```bash
   cd backend
   .venv/bin/alembic upgrade head
   cd ..
   ./scripts/dev.sh
   ```

6. Open **Mailboxes**, read the disclosure, choose **Send only** or **Send and sync**, then complete Google's consent. Sending requests `gmail.send`; synchronization and Gmail read/archive updates use `gmail.modify`. Platform login still requests only identity scopes. Selecting send-only disables synchronization even if Google returns an older read grant.

The default worker polls every 120 seconds (`GMAIL_SYNC_INTERVAL_SECONDS`). `GMAIL_WORKER_ENABLED=false` disables background work for controlled tests. `GMAIL_DAILY_SEND_LIMIT` is an application limit, not a promise about Gmail quotas. Run one API process/replica: this release retains the existing database-backed worker architecture; a Redis deployment is not required. The process must stay awake for timely sends and sync.

Mailbox settings include a sanitized signature, IANA timezone, and daily scheduled delivery window. Outgoing files are explicitly selected in the send review: up to five files, 8 MiB combined before encoding and 12 MiB for MIME. Nothing is attached automatically from a persona or previously uploaded resume. The **Test to myself** action sends only to the chosen connected mailbox and adds a test subject prefix; use a reviewed normal send when testing delivery to a separately designated saved contact.

## Google blocks a test account: `403 access_denied`

If Google says the app is being tested and only developer-approved testers can access it:

1. Check the authorization request's `client_id` against **Google Auth Platform → Clients**. Select the project containing that exact client; a separate `GMAIL_CLIENT_ID` can belong to a different project from platform sign-in.
2. In that project, open **Audience → Test users → Add users**. Add the actual Google account selected for Gmail consent and save. Keep the publishing status **Testing**.
3. Return to the platform's **Mailboxes** page and start a new connection. Select that same account; do not reuse the old error-page URL.

Google may block before returning to the platform. If it does return, the current platform message is generic; use Google's error page to identify this test-user restriction.

Basic Google sign-in requests identity scopes and can work without this test-user entry. Gmail consent requests additional scopes and requires test access while in Testing. Adding a tester does not complete production scope verification. [Google's Audience guidance](https://support.google.com/cloud/answer/15549945?hl=en).

## What Inbox can show

Only addresses on **saved Contacts in the current workspace** are eligible. Search results that have not been saved are excluded. Addresses are parsed and compared exactly after trimming and lowercasing; there is no company-domain expansion, substring match, plus-address folding, or Gmail dot folding.

The backend fetches candidate headers, checks eligibility, and only then requests a matching message's body. A Gmail thread ID alone never authorizes another message's content. Every read rechecks the contact's current saved state, ID and email, so unsaving/deleting a contact or changing its email removes old messages from visibility. Sync also rechecks immediately before fetching and before saving a body, including contact changes committed during the upstream request. Frontend hiding is not the access control. Mailbox and attachment operations also enforce the current workspace.

Inbox supports exact email and email-domain filters, intent, awaiting reply, and pagination. Filters and offsets apply after contact access checks; a domain filter never grants access to unsaved addresses. Awaiting reply means the latest visible message in that conversation is incoming and not classified as automated. Manual follow-up reminders appear in the conversation.

First sync queries the last 30 days, follows pagination, retains a history cursor, and subsequently uses incremental history. Expired cursors trigger bounded initial recovery; previously tracked eligible threads remain discoverable. Messages from Gmail outside Connact.ai can appear when they match the same rules.

Google does **not** offer OAuth scopes limited to named contacts. The authorization can technically access broader mailbox data; the above restriction is enforced by the application. Incoming email bodies are not automatically sent to AI. Email HTML is sanitized, remote images are removed, and attachments are served only through scoped download endpoints. Administrators have no mail-body browsing endpoint.

## Sending, replies and reminders

Review a draft, choose the connected sender, and explicitly confirm recipient, subject and send time. A send command freezes that content revision and checks saved-contact identity, address, suppression, placeholders and sender permission. Retries with the same idempotency key return the same command. `sent` means Gmail accepted the message; it does not prove delivery or a human read.

For replies, open the original Inbox conversation. Sending retains Gmail thread ID, matching subject, `In-Reply-To` and `References`; the reply recipient must remain the saved contact belonging to that conversation. Read/archive controls update Gmail for visible messages.

Incoming contact mail pauses that contact's unsent scheduled messages. Reauthorization, failed synchronization, changed contact identity and suppression also block sending as applicable. Users must review paused work and explicitly resume it. There is an unavoidable interval between the last reply check and a send; Gmail cannot provide absolute exactly-once delivery or guarantee that no reply arrives during that interval.

A timeout, invalid send response, server restart during sending, or ambiguous upstream failure is recorded as an unknown outcome. Do not blindly retry: inspect Gmail Sent and the stored message identifier first. Manual follow-up tasks are reminders only. Reaching their due time never sends a message or creates an automated next step.

Disconnecting destroys local credentials and stops pending sends. The default also deletes imported mail data; it does not delete mail from Gmail. To remove the Google-side grant, use [Google account connections](https://myaccount.google.com/connections). Revoking a shared OAuth client's grant may also affect other permissions granted to that client.

## Live acceptance

Automated tests replace the Google HTTP boundary and use isolated databases. They are evidence for implementation behavior, not real mailbox authorization or delivery.

For each environment, verify mailbox consent and refresh, then use only an explicitly designated test recipient. Confirm the received test message, reply from that mailbox, and verify that the reply appears under the correct workspace/mailbox. Also include an unrelated email, an unsaved search candidate, and an unrelated sender in a known thread; their bodies must not appear. Verify a reply pauses a scheduled send, a due reminder sends nothing, and disconnect removes access. Record actual results before claiming live acceptance.

### Verification on 2026-09-13

- Final SQLite regression: 276 passed, one PostgreSQL-specific case skipped. A full PostgreSQL regression previously passed 254 cases; after subsequent hardening, 85 Gmail cases also passed on isolated PostgreSQL. The final filter and concurrent-contact-change additions passed on SQLite. Deprecation warnings come from the existing Starlette test stack.
- Four Gmail browser integration tests passed through the real Next.js proxy and FastAPI using an isolated fake Google transport, including sending, replies, attachments, filtering and pagination. Seven existing writing regression cases also passed earlier in this change.
- Both Gmail migrations passed upgrade, downgrade and re-upgrade checks, with existing records preserved and SQLAlchemy/Alembic schema comparison clean.
- The local database was cloned before migration; the running app is at `g531ec641012`. Existing table row counts were preserved. Local API and frontend proxy health returned PostgreSQL `ok`.
- The local OAuth client was updated with the mailbox callback after reproducing Google's `redirect_uri_mismatch`. The connection button then reached the real Google sign-in page successfully.
- No Gmail mailbox has yet been granted access in this acceptance run. Gmail API enablement, token refresh against a real mailbox, delivery and receipt of a real reply remain to be verified with the owner. Production deployment and Google production review have not been performed by this change.

Automated evidence is retained locally in `work/gmail-verification/`; it contains no live mailbox bodies or credentials.

Follow-up on 2026-09-14: a real connected mailbox returned `403 accessNotConfigured` / `SERVICE_DISABLED` because Gmail API was disabled in the local OAuth project. Enabling the API restored a real profile request to HTTP 200 and a subsequent Inbox sync completed with no error. That workspace had zero saved contacts, so no messages were imported. Real message delivery and contact-reply import remain unverified. The backend now distinguishes disabled API, missing scopes, organization policy and rate-limit reasons using fixed messages without exposing upstream diagnostic text.

Public rollout requires the Google review appropriate to Gmail scopes. Testing-mode grants can expire; a connected identity-only login does not prove Gmail production approval. See Google's [scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes), [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server), [synchronization guide](https://developers.google.com/workspace/gmail/api/guides/sync), [thread requirements](https://developers.google.com/workspace/gmail/api/guides/threads) and [Workspace user-data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

中文配置和验收步骤见 [Gmail 接入说明](gmail-integration.zh-CN.md)。
