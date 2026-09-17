Please develop Connact.ai Phase 4: Batch Campaign Templates and Statistics.

Confirmed constraints: Personal workspaces can connect to multiple Gmail mailboxes; team support is reserved for future work. English is the default interface language, with Simplified Chinese available as an option; email language is controlled independently. Finance is the core domain, while Academic remains a placeholder and provider contract. No phase includes automated email sequences. Every module must remain independently accessible; do not force users through a step-by-step wizard. Do not present Mock behavior or the HTML demo as a live integration.
Admin backend has been listed as Soon to be scheduled, not within the scope of P1–P4 implementation; only retain Coming Soon entry and scope description, no real management operations are open. Platform admin and personal workspace Owner are different roles.
First inspect the workspace, AGENTS.md, and existing implementation, then provide a short implementation order and proceed with development. Extend the current data model and modules instead of rebuilding the project. Verify third-party capabilities against current official documentation. When credentials are unavailable, use an explicitly labeled Mock; live failures must never silently fall back to simulated success. Deliver code, migrations, startup instructions, key verification results, and a clear list of live items that remain unverified. Any live sending must use only test recipients specified by the user.

Develop Phase 4 on top of the first three phases: batch campaigns, template and snippet management, basic analytics, settings refinement, and the Academic provider contract. Automated email sequences, team collaboration, billing, and a live Outlook integration remain out of scope.

Campaign definition: a batch of users who have explicitly approved independent emails; no capability to automatically send a second email after the first. Save CampaignRecipient contact, persona version, content snapshot, email, time, and result.

After user selects a list, generate and preview emails individually, displaying missing variables, duplicate contacts, no email, blocked, attachments, limits, and time issues. Allow explicit exclusion of problematic contacts, cannot silently skip. After user approval, send individually to each contact, not using group To/CC. Reuse phase two scheduling, idempotency, and phase three reply protection.

Support campaign pause/resume/termination, individual exit, partial failure, and progress. Resume recalculates the valid window, not instantly resending overdue tasks. Retry unknowns must be verified first, no blind resending. Template updates after content approval do not affect existing tasks.

Templates/Snippets: Finance classification, create/edit/version/archive; Academic only example classification. Batch AI uses the same facts and manual adoption rules as phase one, no temporary personalization content is generated in the backend.

Analytics: number of officially sent emails and deduplicated users, number of manual replies, detected bounces, unsubscribes, campaign progress, and manual tasks. Clearly define events, time windows, denominator, and deduplication criteria. Testing and Mock are independent, no fabricated delivery/open/click rates. Improve configuration, data export/deletion, errors, and Chinese/English copy.

Academic: Keep Coming Soon; design academic personas and Mentor extensions, candidate lists, and link with shared modules. Implement MentorDataProvider/MentorMatchingProvider contract tests, reserve JSONL/SQLite/Postgres/External registration skeletons. Return Unavailable explicitly if not implemented, no fake mentors or empty success results.

Acceptance: Preview and sent content must be consistent per user; repeated starts do not result in repeated sends; pause/exit/reply/unsubscribe take effect; statistics can be verified from events. Complete phase four regression, operation documentation, real verification records, and public external launch checklist. Do not treat completed design documents or demos as the product being complete.
