# Customer registration and administration

The previously verified Render trial uses public email registration and a separate administrator account. Website: <https://connact-ai.onrender.com>. The current code also supports replacing password login with Google sign-in; follow [Google client creation and migration](google-sign-in.md) before switching a deployment. This code change alone does not configure or deploy Google credentials. Deployment details and free-plan limits are in [render-trial.md](render-trial.md). Gmail sending is not connected; users can copy reviewed messages or export an unsent `.eml` file.

## Access

- `AUTH_MODE=local`: private localhost development workspace.
- `AUTH_MODE=open`: email registration without invitation; each account has an independent workspace. Existing invited accounts keep their data and passwords.
- `AUTH_MODE=invite`: optional restricted registration retained for other installations.
- `AUTH_PROVIDER=google`: Google sign-in/sign-up with verified identities; password login/join endpoints are disabled. Requires backend OAuth credentials and an exact registered frontend callback. `AUTH_PROVIDER=password` retains the legacy behavior described below during migration.
- Public modes require an exact HTTPS `PUBLIC_ORIGIN`. Sessions use HttpOnly, SameSite cookies and expire after `SESSION_DAYS` (default 7). Login and registration retain server-side rate limits.

Registration only accepts email and password (at least 12 characters); it cannot assign administrator roles. The login form also accepts the reserved `admin` username. Registration discloses administrator access to saved information and uploaded files.

## Administrator setup

Set `BOOTSTRAP_ADMIN_PASSWORD_HASH` to a scrypt hash generated locally by `app.routers.auth.password_hash`. Never commit the password or its deployment hash. The Render Docker startup runs `python -m app.bootstrap_admin` after migrations and creates the reserved `admin` account if absent. Existing administrator passwords are never overwritten on restart. Remove the bootstrap variable after setup if desired. Other launchers can run that module explicitly before starting the server.

The `/admin` console provides account search, pagination, registration and last-login times, record counts, saved personas and revisions, contacts and profiles, evidence and assessments, drafts, search/people jobs, writing jobs, and uploaded originals with extraction results. This is read-only account inspection; password reset, account deletion and role-editing UI are not included.

Every `/api/admin/*` request checks a valid session and the current database administrator role. Regular users cannot enumerate other accounts or download their documents. No administrator password hashes, session tokens or provider API keys are returned. Saved HTML and provider output are displayed as text, and original files download as attachments.

## Files and operation

Original PDF/DOCX uploads (maximum 8 MB) are stored in PostgreSQL together with their metadata. A missing application disk does not prevent parsing or download of these originals. Older local files still available at startup are copied into the database; a file already lost before this version cannot be recovered. On Render Free, the database remains limited in capacity and expires after 30 days.

Run one backend process. People, document and writing jobs persist in the database; ambiguous interrupted provider calls surface as failures rather than silently repeating charges. Provider keys remain exclusively on the backend. Public registration does not configure or grant access to paid upstream providers.

Google sign-in validates Google's verified email claim; legacy password registration does not verify email. Gmail mailbox OAuth, reviewed sending and contact-filtered Inbox now have an implementation; see [Gmail configuration and acceptance](gmail-integration.md) before enabling them in a deployment. There is no self-service password recovery or per-customer billing. Back up the database, including `document_files`, to preserve account data and original uploads; back up Gmail encryption keys separately.
