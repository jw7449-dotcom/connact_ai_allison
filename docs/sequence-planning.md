# Local sequence planning

Sequences organizes saved email drafts into a connected workflow. It is available from the left navigation at `/sequences`; reusable single-email content has its own `/templates` library. These are separate from the existing future sending modules.

## Create and complete a sequence

1. Choose **New sequence**, give it a name and choose its email language.
2. Start with **Plan with AI**, **Step template**, **From drafts**, or **From scratch**. The default step templates are Networking, Recruiting and Reconnect. Draft selection order becomes step order, and each imported email is copied into an independent sequence draft.
3. In **Build steps**, add, remove or move email cards. Step settings include purpose, delay in days, and new thread or reply. The first email starts a new thread on day 1; subsequent delays are relative to the preceding step. Manual plans support up to 20 email steps.
4. Open **Write email** on any card. The full Assisted / Prompt / Template editor and durable AI suggestions are available for that step. Reply previews inherit the preceding thread's subject. Saving/reordering sequence steps preserves the original drafts in Email Studio.
5. In **People & context**, choose a preview contact and sender persona and apply them to the emails. Individual writing editors can further adjust their context.
6. In **Preview & review**, inspect every email, including inherited reply subjects and resolved variables. Missing content, recipients or variable values prevent review. Editing a reviewed draft or its context invalidates that sequence's review state.
7. Use **Save as template** to reuse the complete order, timing, thread settings and email content. Recipient and persona IDs are not included in portable templates.

Sequence planning does not connect a mailbox, enroll a contact for delivery, schedule a send, or execute automatic follow-ups. The visible intervals describe the plan. Reviewed means the content has passed local review; it does not mean a message was delivered.

## AI step generation

AI planning uses the existing model catalog and configured provider route. A plan may contain 1–8 AI-generated steps. Each validated step is saved to a background job before requesting the next one, and the interface shows completed-step progress. This is incremental step generation, not token streaming.

The finished plan replaces sequence steps atomically. Existing sequence drafts remain available. A sequence revision, email revision, recipient or sender change during generation prevents replacement. Failures remain visible and can be retried; there is no automatic provider or Mock fallback. Queued jobs survive restarts; an interrupted running job reports a restart error and requires an explicit retry, since a provider request may already have completed.

`AI_MODE=mock` produces a clearly labeled deterministic example. `AI_MODE=live` invokes the selected upstream model. A configured model alone is not proof of a successful call.

## Portable step templates

Choose **Step templates → Download JSON** to obtain a valid starting file. Edit it and select **Upload steps JSON**. The browser accepts files up to 250 KB; the API validates field lengths, supported fields, step count, first-step semantics and HTML. Unknown fields and invalid delays produce an error instead of partially importing a plan.

```json
{
  "schema_version": 1,
  "name": "Two-step introduction",
  "description": "A brief introduction and one considerate follow-up.",
  "steps": [
    {
      "title": "Introduction",
      "purpose": "Ask for a short conversation.",
      "delay_days": 0,
      "thread_mode": "new_thread",
      "subject": "An opportunity to connect",
      "body_html": "<p>Hi {{name}},</p><p>Would you be open to a brief conversation about your work at {{company}}?</p><p>Best,<br>{{sender_name}}</p>"
    },
    {
      "title": "Follow-up",
      "purpose": "Follow up politely and leave the timing to the recipient.",
      "delay_days": 5,
      "thread_mode": "reply",
      "subject": "",
      "body_html": "<p>Hi {{name}},</p><p>I wanted to follow up on my note. I understand if your schedule is full and appreciate your consideration.</p>"
    }
  ]
}
```

`GET /api/sequence-templates/schema` exposes the schema. Sequence templates use `/api/sequence-templates`; single-email templates use `/api/writing-templates` and a different shape (`name`, `description`, `category`, `subject`, `body_html`). Both libraries are stored in the user's workspace. Templates can be downloaded, customized and uploaded as independent reusable copies.

## Persistence and validation

Migration `c183df901008` creates sequence plans, steps, background planning jobs and both template libraries. Run `./scripts/dev.sh` to apply migrations and start the local stack. Existing drafts and contact data are preserved.

Backend contract tests cover workspace isolation, imported draft independence, revision conflicts, inherited subjects, review invalidation, invalid uploads, partial AI failure and generation conflicts. Browser tests exercise the complete local sequence and writing workflows against an isolated Mock workspace. Apollo product observations and the limits of the signed-in trial are documented separately in [Apollo writing and Sequence trial](apollo-sequence-writing.md).

### Verified on 2026-09-09

- Full backend suite: **115 passed, 1 skipped**. The skipped check is optional; the suite uses an isolated database and no paid provider calls.
- Browser regression: **18 workflows passed across the main run and targeted reruns after fixes**, covering writing, sequences and the existing persona/contact flow. The mobile sequence editor fits a 390px viewport without horizontal page overflow.
- Frontend TypeScript and production build passed. Migration upgrade/downgrade/upgrade and Alembic model-drift checks passed on an isolated database; the local PostgreSQL workspace was then migrated successfully.
- Live AI: `qwen-plus` generated and saved three sequence emails through the configured Bailian route, with delays of 0, 4 and 7 days and inherited reply subjects. The result can be reopened locally as `Finance networking · Live AI validation`. A first attempt interrupted by the development server's reload surfaced a restart error and preserved the sequence; a fresh plan completed all three steps.
- The live sample has no assigned contact and remains a draft. No email was sent, no recipient was enrolled, and no deployment was performed.
