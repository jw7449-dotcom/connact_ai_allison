# Templates belong to a persona

Date: 2026-09-19
Status: approved, not yet implemented

## Problem

Writing templates are workspace-level. Nothing in the product connects a
template to the persona it was written for. `writing_templates` has no
`persona_id`, and neither way of creating a template supplies one:

- Email Studio's "save as template" posts `name`, `description`,
  `category`, `subject`, `body_html` — the draft's persona is dropped.
- The `.json` upload path posts the same shape.

So a workspace accumulates a flat pile of templates that apply to every
persona equally, which is wrong for a product where a persona is the whole
notion of "who I am when I write this". A finance analyst persona and an
academic persona need different libraries.

This spec covers only the ownership move. The first-run onboarding wizard
is a separate follow-on (see Out of scope).

## Decisions

| Question | Decision |
| --- | --- |
| Ownership | One template belongs to one persona. FK, cascade delete. |
| Templates nav | Removed entirely. No redirect. |
| Templates with no persona | Cannot be created. Existing ones are backfilled. |
| Starter templates | Stay code constants, global, unchanged. |

## Data model

Add to `writing_templates`:

```
persona_id: Mapped[str] = mapped_column(
    ForeignKey("personas.id", ondelete="CASCADE"), index=True
)
```

Not nullable. Every row has an owner once the migration finishes, so the
database enforces the invariant rather than trusting the API to. The
migration adds the column nullable, backfills, then tightens it — see
below.

`DEFAULT_TEMPLATES` in `app/routers/writing_templates.py` stays a list of
code constants returned alongside every persona's templates. They are not
database rows and need no migration.

## Migration

One Alembic revision, in four steps so the column can end up `NOT NULL`:

1. Add `persona_id` as nullable, with its index and the FK
   (`ON DELETE CASCADE`).
2. Backfill: for each workspace that owns templates, attach them to that
   workspace's oldest persona, ordered by `Scoped.created_at`.
3. For a workspace that owns templates but has no persona at all, create an
   empty persona labelled `Persona 1` and attach them to it. Losing a user's
   saved templates is not acceptable; an empty persona is recoverable.
4. `ALTER COLUMN persona_id SET NOT NULL`. Steps 2 and 3 together leave no
   null rows, so this cannot fail on well-formed data — and if it does, the
   migration aborts rather than silently admitting orphans.

Downgrade drops the constraint, the index and the column. It does not delete
the `Persona 1` rows — a downgrade should not destroy data the user may have
since edited.

## API

All routes in `app/routers/writing_templates.py`.

| Route | Change |
| --- | --- |
| `GET /writing-templates` | Requires `persona_id` query param. Returns that persona's rows plus the three defaults. |
| `POST /writing-templates` | Requires `persona_id` in the body. 422 without it. |
| `PUT /writing-templates/{id}` | Verifies the row's persona is in the caller's workspace. |
| `DELETE /writing-templates/{id}` | Same check. |

`persona_id` is validated against the caller's workspace on every write, so
a template cannot be attached to another workspace's persona. This matters
because `Scoped` gives row-level workspace isolation but says nothing about
whether a supplied foreign key belongs to the caller.

## Frontend

**Personas page** gains two tabs:

- **Background** — the existing persona form, unchanged.
- **Templates** — `writing-template-library.tsx` rendered for the selected
  persona.

`writing-template-library.tsx` takes a required `personaId` prop and sends
it on load and on save.

`writing-templates-page.tsx` is deleted.

**Navigation**: the `/templates` entry is removed from the sidebar in
`workspace.tsx`, and its route case is removed. The path stops resolving.
No redirect — the section is gone, not moved.

**Email Studio**: the template picker loads templates for
`draft.persona_id`. When the draft has no persona selected, it shows only
the three defaults, and "save as template" is disabled with the reason
stated inline ("Choose a persona before saving a template"). This is what
prevents new ownerless templates, and it teaches the ownership rule at the
moment it first matters.

## Testing

Existing tests that will fail and must be updated:

- `frontend/tests/writing.spec.ts:431` — the template upload path now runs
  through Personas → Templates rather than a top-level page.
- `frontend/tests/workflow.spec.ts:150` — asserts `/templates` among the
  future routes.

New backend tests:

- A persona's templates are not visible when querying another persona.
- Deleting a persona deletes its templates.
- `POST` without `persona_id` returns 422.
- `POST` with a persona belonging to another workspace is rejected.
- Migration backfill attaches existing rows to the oldest persona, and
  templates in a persona-less workspace land on a created `Persona 1`.

New frontend test: saving a template is disabled until a persona is chosen.

Run the suite with `./scripts/test-e2e.sh`, never bare `npx playwright test`
— the latter runs against the shared dev database and produces false
failures from leftover state.

## Out of scope

The first-run onboarding wizard (upload a resume, paste or upload your usual
templates, both forming Persona 1) is the follow-on piece. It depends on
this spec's data model and gets its own design. The paste-text and
PDF/DOCX template import path is part of that work, not this one; the
existing "save from Email Studio" and `.json` upload paths carry this spec.
