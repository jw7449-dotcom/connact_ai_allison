# Google sign-in setup

Connact.ai supports Google OAuth 2.0 / OpenID Connect sign-in in its existing FastAPI backend. The supplied `google-oauth-reuse-kit.zip` was reference material for the protocol and stable Google identity mapping; the Flask application itself is not run or copied into the service. This sign-in requests only `openid email profile` and does not connect Gmail or grant mail access.

## Create a development OAuth client

1. Open [Google Auth Platform](https://console.cloud.google.com/auth/overview). Select or create a project such as **Connact.ai Development**. Click **Get started** if this is its first OAuth application.
2. Enter **Connact.ai** as the app name, choose your support email, select **External** as the audience, and enter a contact email. Complete the setup. Keep the development project in **Testing**.
3. In **Data Access → Add or Remove Scopes**, select only `openid`, `https://www.googleapis.com/auth/userinfo.email`, and `https://www.googleapis.com/auth/userinfo.profile`. No Gmail, Drive, or Contacts scope is needed.
4. In **Clients → Create client**, choose **Web application**. Name it **Connact.ai Local Web**. Under **Authorized redirect URIs**, add the exact address below, which matches the repository's default `PUBLIC_ORIGIN`:

   ```text
   http://127.0.0.1:3100/api/auth/google/callback
   ```

   If you prefer opening the app using `http://localhost:3100`, use `PUBLIC_ORIGIN=http://localhost:3100` and register `http://localhost:3100/api/auth/google/callback` instead. You may register both on the development client, but always open the app through its configured origin. The callback goes through the frontend on port **3100**, not the backend on port 8000. **Authorized JavaScript origins** can remain empty for this server-side authorization-code flow.

   Docker Compose passes `PUBLIC_ORIGIN` to both services. Local page navigation from the other loopback hostname automatically redirects to the configured hostname on the same port before sign-in, so the OAuth state cookie and callback use the same host. For a frontend started outside Compose, set the same `PUBLIC_ORIGIN` in its environment (the default is `http://127.0.0.1:3100`). API origin checks remain strict.
5. Click **Create**. Save **Client ID** and **Client secret**, and download the JSON while offered. The complete secret is visible/downloadable when it is created; if lost, create a new secret for the client. These are OAuth credentials, not a Google API key. Keep the JSON outside the repository and do not paste its secret into chat.

Google's current Testing policy exempts requests limited to these basic identity scopes from its test-user requirement and seven-day authorization expiry. Adding your email under **Audience → Test users** is still a convenient way to organize testing. See [Google's setup guide](https://developers.google.com/workspace/guides/configure-oauth-consent), [client and secret management](https://support.google.com/cloud/answer/15549257?hl=en), and [Audience settings](https://support.google.com/cloud/answer/15549945?hl=en).

## Configure and verify locally

Put the actual values in the private root `.env`; never put the secret in `NEXT_PUBLIC_*`, source files, browser storage, or Git:

```dotenv
AUTH_MODE=open
AUTH_PROVIDER=google
PUBLIC_ORIGIN=http://127.0.0.1:3100
GOOGLE_CLIENT_ID=replace-with-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=replace-with-client-secret
```

Install the backend dependencies, run `alembic upgrade head` from `backend`, and restart the backend and frontend (or use `./scripts/dev.sh`). Open the exact configured frontend origin and click **Continue with Google**. `/api/auth/session` must report `provider: google`, `google_configured: true`, and after completing Google's consent, `authenticated: true`. Sign out and sign back in to verify the same workspace is restored. Real local sign-in was verified on 2026-09-09 as recorded below; production deployment is separate.

`AUTH_MODE=local` intentionally bypasses all login for private development. It must be changed to `open` or `invite` to exercise Google sign-in. `AUTH_PROVIDER=password` retains the old login for a staged migration; once set to `google`, both password registration and password login are disabled. Existing deployments without `AUTH_PROVIDER` keep their prior password behavior rather than changing access before credentials are ready.

## Production client

Use a separate production Google project/client. For the existing frontend domain, set the authorized redirect URI to:

```text
https://connact-ai.onrender.com/api/auth/google/callback
```

On the **Render backend** set `AUTH_MODE=open`, `AUTH_PROVIDER=google`, `PUBLIC_ORIGIN=https://connact-ai.onrender.com`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`. Keep the frontend's `PUBLIC_ORIGIN` aligned and `BACKEND_URL` pointing to its backend. Do not upload the client secret to the frontend service. Deploy the code and migration before switching the authentication provider. Only switch once the production client is ready and existing account access has been checked.

Configure the production app's real homepage, support contact, privacy policy and owned domains, publish it in **Audience**, and follow Google's brand verification requirements. Production clients should not include localhost redirect URIs. Basic sign-in scopes do not require sensitive-scope review; brand requirements are separate. See [Google's production guidance](https://developers.google.com/identity/verification/authentication-policy-compliance).

The public homepage is `/about` and the privacy policy is `/privacy`; both are readable without signing in. Set `PUBLIC_SUPPORT_EMAIL` on the **Render frontend** to the confirmed public support address. Website verification files belong in `frontend/public/` and must remain available after verification.

### Preserve the existing administrator

1. Deploy migration `e318ca421010` and configure the production OAuth client while keeping `AUTH_PROVIDER=password`.
2. Sign in as the existing `admin`, open `/admin`, and enter the intended Google email under **Administrator Google sign-in**. Click **Link Google account** and complete Google's identity check.
3. Confirm that the server reports `google_linked: true` and that the original administrator workspace remains accessible. The reserved username, user ID, data and role are preserved; no new administrator is created.
4. Change the backend to `AUTH_PROVIDER=google`, redeploy, then sign out and sign back in through Google. Verify the same administrator workspace and permissions.

The binding request is available only to the authenticated reserved administrator. It binds one-use OAuth state to the chosen email and the initiating login session. The callback checks that this session is still valid, verifies the Google identity, rejects existing account/identity conflicts, and replaces the administrator's old sessions. It never promotes an ordinary Google user by matching an environment email.

## Existing accounts and implementation boundaries

- Google identity uses its signed, stable `sub`, not the email as an identity key. Subsequent email changes do not move the workspace. Every new user gets a separate server-assigned workspace.
- An existing account with a Google-hosted verified email can be linked to Google while retaining its saved data. First-time linking revokes old account sessions before issuing the verified user's new session, since legacy password registration did not verify ownership of that email. For third-party email domains where Google does not assert current ownership, linking also requires an existing authenticated session; otherwise the UI directs the user to account support. No account is silently merged with a different Google identity.
- The reserved legacy `admin` username is linked only through the explicit administrator flow above; it is never automatically migrated or assigned to another Google user. Ordinary registration does not grant an administrator role.
- Invite mode checks an invitation only when creating a new account, binds any email restriction to Google's verified email, and consumes a place in the same transaction as account creation.
- The callback verifies one-use browser-bound state, PKCE, nonce, signature, issuer, audience, and expiration. Google access/ID tokens are never persisted. Local session tokens remain opaque and revocable; no Google account password is handled by Connact.ai.
- The Next.js proxy forwards redirects and each `Set-Cookie` header to the browser without following Google's authorization URL on the server. OAuth callback responses suppress referrers.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Google button says server configuration is pending | Both OAuth values must be present on the backend, followed by a restart. |
| The app opens without any login | `AUTH_MODE` is still `local`; set it to `open` for Google sign-in. |
| `redirect_uri_mismatch` | The registered callback must equal `PUBLIC_ORIGIN + /api/auth/google/callback`, including protocol, host, port and path. |
| Login request expired or invalid | Start again using the same browser and configured frontend origin; state expires after ten minutes and is one-use. |
| Existing third-party email needs linking | Establish the existing account session before migrating the provider, then link Google, or arrange a verified account migration with the administrator. |
| The original username `admin` cannot use Google | Complete the explicit binding from `/admin` while password login is still enabled; new Google users never inherit that role. |

Official protocol reference: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

## Validation on 2026-09-09

The full backend suite passed 165 tests on a disposable local PostgreSQL database, including OAuth identity checks, workspace isolation, invitation row locking and page-profile preparation. Fresh Alembic upgrade and schema check passed with no drift; the disposable database was removed. Five Google UI/proxy tests, nine authentication recovery browser tests and four people-state browser tests passed. The production Next.js build passed. Google endpoints in these automated tests used synthetic credentials/signed test tokens. Live SerpAPI/Apify page verification is documented separately in [people-provider-verification.md](people-provider-verification.md).

The `Connact.ai Local Web` credentials were subsequently configured in the ignored root `.env` (mode `0600`) with `AUTH_MODE=open`, `AUTH_PROVIDER=google`, and `PUBLIC_ORIGIN=http://127.0.0.1:3100`. The existing local Docker backend/frontend images were rebuilt and recreated while preserving the PostgreSQL and upload volumes. Both health endpoints returned HTTP 200; anonymous draft access returned 401. The local database migrated to `d247ab731009`.

A real Chrome sign-in completed through Google's callback (HTTP 302) at 2026-09-09 23:53 Asia/Shanghai. The browser displayed the authenticated independent workspace. The database contained one Google identity, one non-admin user and one local login session, with zero remaining OAuth-state rows. The original `local-personal` workspace and its one draft remained intact; the new Google user owns a separate workspace. The local client has only the registered loopback callback and is not a Render/production deployment.
