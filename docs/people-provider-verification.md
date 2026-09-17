# People discovery and enrichment

Discovery, professional details and email remain separate provider jobs and may be used without a persona or an email draft. The search workflow now automatically prepares professional details for the requested result page.

- **Discover:** SerpAPI Google search targets `site:linkedin.com/in/`. Google titles/snippets are discovery evidence, not full profiles or proof that every filter matches. Canonical LinkedIn URLs identify results; repeated searches preserve saved edits and enrichment.
- **Professional profile:** Each new search page automatically schedules Apify `harvestapi/linkedin-profile-scraper`, using `queries: [one public LinkedIn URL]` and `Profile details no email ($4 per 1k)`. Only returned professional fields are stored: summary, headline, location, work experience, education and skills. Missing fields remain missing. No LinkedIn cookies or browser login are supplied.
- **Email:** The user selects Apollo or Apify. Apollo `people/match` requires API-plan access and confirms the same canonical profile. Apify's separate `Profile details + email search ($10 per 1k)` mode is an explicit paid action. An Apollo denial never automatically starts Apify. Personal-typed emails and common consumer-mail domains are excluded from Apify candidate selection. Missing email type is disclosed as unknown. Empty results preserve an existing contact address.
- **Phone:** Phone lookup is not enabled. Contacts explicitly report `phone_status: not_requested`; empty phone data is listed as missing. Neither the public-profile task nor email task asks Apollo to reveal a phone number.
- **Verification:** No address is considered verified merely because a LinkedIn profile has a verified badge, the Actor's marketing mentions SMTP checks, or an email exists. Apollo's explicit email status is retained as a provider claim. Apify's result status is retained in the job/source evidence, while the address stays unverified by this application.

## Observed live checks

### 2026-09-09 current-key check

The current Apify account API returned `FREE` with USD 5 monthly usage credits. A single no-email profile run (`2UfBooeLLOc3OQWdQ`, canonical LinkedIn `/in/seanwhill`) succeeded with the matching identity, a biography, 4 work entries, 1 education entry and 7 skills. The reported charge was USD 0.004. This confirms the current key can retrieve professional details; an additional subscription is not required for this feature. It does not guarantee every public profile exposes every field.

The complete backend page workflow was then exercised against live SerpAPI and Apify using an isolated two-person search page. It advanced from discovery through `pending: 2` to `ready: 2, failed: 0`, then completed. The profiles contained 4/5 work entries, 1/2 education entries, and 7/0 skills respectively. Both kept `email_status: not_requested`; only one search job and two profile jobs existed. Repeating the same search reused the same completed job and left the job count at three. This validates the live two-person backend pipeline, not ten-person coverage or a production deployment.

Mocked browser integration separately verifies that results are held until preparation completes, details appear immediately even while their local refresh GET is delayed, and opening a person makes no enrichment-creation request. Backend tests cover failed profiles retaining their rows, restarts retaining run IDs, local throttling, cache invalidation and no automatic email mode. Safe summaries: `work/google-oauth-profile-update/profile-result-summary.json` and `work/google-oauth-profile-update/live-page-summary.json`.

If monthly usage outgrows the free allowance, the current [Apify pricing page](https://apify.com/pricing) lists Starter at USD 19/month. The [profile actor](https://apify.com/harvestapi/linkedin-profile-scraper) lists the selected no-email mode at USD 4 per 1,000 profiles (about USD 0.04 for ten new results); account credits, actual charged events and future price changes still apply. Apollo's previously observed enrichment-plan restriction does not block Apify professional details.

### Earlier 2026-09-08 checks

| Check | Observed outcome |
|---|---|
| SerpAPI, one finance query | HTTP 200, 10 LinkedIn results |
| Apify, one discovered public profile | SUCCEEDED; 5 work entries, 3 education entries, 0 skills; one profile event, USD 0.004 |
| Apollo, same canonical profile | HTTP 403 / API_INACCESSIBLE; current account has no `people/match` access |
| Apify email search, same finance profile | SUCCEEDED; `emails: []`; one profile-with-email event, USD 0.010 |
| Apify email search, Tim Zheng public business profile | SUCCEEDED; one non-free-domain address returned; provider reported `valid`, `deliverable=true`, `catchAllDomain=false`, `validEmailServer=true`, `qualityScore=80`; USD 0.010 |

Total observed Apify charge for these three probes: **USD 0.024**. The first two submissions set `maxTotalChargeUsd=0.05`; the additional business-email probe set `maxTotalChargeUsd=0.01`. Each used `timeout=180`, `memory=256`, and a single URL. The additional profile URL was verified from [Tim Zheng’s public LinkedIn profile](https://www.linkedin.com/in/tim-zheng) before the run. These checks demonstrate real discovery, professional-profile extraction, and email retrieval. The application still labels the returned email unverified and preserves the provider’s check results separately. A two-person email sample is not a coverage estimate or a guarantee of delivery; no email was sent. Provider coverage and prices may change.

Actor input schema was read from the official Apify build API for build `0.0.135`, then exercised with the account's server-side credentials. References: [Actor documentation](https://apify.com/harvestapi/linkedin-profile-scraper), [Actor API](https://apify.com/harvestapi/linkedin-profile-scraper/api), [Apify run API](https://docs.apify.com/api/v2/actors-runs-post).

## Durable API contract

- `POST /api/finance/search/jobs` accepts the existing search filters and returns HTTP 202 `{job, cached}`. Discovery commits the requested page, then the search waits in `result.phase: "profiles"` while durable profile child jobs settle. Only the requested page (at most 10 people) is prepared; subsequent pages require a page request. Search results become available after all profiles succeed or report an explicit failure. A failed profile does not fail discovery or hide that person.
- `result.profile_progress` reports `total`, `ready`, `failed`, `skipped` and `pending`. `result.profiles` stores per-contact job IDs, cached flags, statuses and errors; completed `items` include the corresponding `profile_prefetch` state and already stored `professional` data. The search drawer has no required profile-fetch button. All search/detail GET endpoints only read local data.
- `GET /api/finance/search/jobs` lists the most recent 20 searches in the authenticated workspace. `GET /api/people/jobs/{id}` returns a job and, after success, its current contacts/results.
- `POST /api/contacts/{id}/jobs` accepts `{kind: "profile" | "email" | "email_apify", force?: false}`. `email` means Apollo in live mode. A request contains one contact.
- `POST /api/people/jobs/{id}/retry` resumes an explicitly retryable failure; submitted Apify jobs keep the original upstream run ID.
- Contact responses include `professional`, `missing_fields`, and recent `jobs`, alongside existing `sources`, `domains`, and `assessments`.
- Statuses: `queued`, `running`, `waiting`, `succeeded`, `failed`. Searches cache for one hour; successful profile/email jobs cache for `PEOPLE_CACHE_HOURS` (168 by default). Manual contact identity/context edits invalidate related caches and reject stale in-flight results.
- Automatic profile preparation reuses recent failed profile jobs as well, avoiding repeated paid failures when refreshing or changing search filters. Non-retryable or uncertain submissions remain blocked until explicitly reviewed; automatic work never starts a replacement run for them. Search cache fingerprints were versioned so a new search cannot reuse an older discovery-only page as a fully prepared result.
- Readiness is checked against current child-job invalidation and the stored professional profile, not just the historical page status. Editing a contact or removing its profile makes an old saved result report unavailable; a new explicit search bypasses that stale cache and prepares the current identity. Reading history/details never triggers that new work.
- Older discovery-only saved searches remain readable. A matching stored professional snapshot is marked ready; otherwise the person is marked unavailable with an explicit instruction to search again for automatic preparation.
- At most ten automatic Apify profile runs are submitted concurrently in this single-process worker. Each run retains `APIFY_MAX_CHARGE_USD` (USD 0.05 by default), so one ten-person page can submit at most ten individually capped runs (USD 0.50 combined configured ceiling). The typical selected actor price is lower than this ceiling. Local per-provider throttling defers work for 61 seconds without consuming failure retries or treating an unsubmitted request as an uncertain paid run.
- Navigating away does not cancel a job. Search history and contact task status restore from the database. On server restart, known Apify run IDs resume polling; an uncertain paid submission is surfaced for provider-console review instead of automatically submitted again. Transient run/dataset reads retry with bounded backoff.

The worker is intended for the current **single API process** deployment. Use one Uvicorn worker. A multi-process deployment needs a shared lease/queue strategy for startup recovery and account-wide rate/billing controls. Provider keys stay on the backend; never add them to public frontend environment variables.

Migration `c216770d1002` adds the durable people jobs table after writing migration `9c3b2f1a7001`. Public professional details use the existing `ContactDomainProfile` JSON storage; no destructive contact migration is required.
