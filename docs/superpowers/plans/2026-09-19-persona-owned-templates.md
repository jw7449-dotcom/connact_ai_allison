# Persona-Owned Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every writing template belong to exactly one persona, and remove Templates as a top-level section.

**Architecture:** Add a non-nullable `persona_id` FK to `writing_templates`, backfilled by an Alembic migration. The API requires a persona on every read and write and validates it against the caller's workspace. The frontend moves the template library into a tab on the Personas page, deletes the standalone Templates page and nav entry, and gates "save as template" in Email Studio behind choosing a persona.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16, React, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-19-persona-owned-templates-design.md`

**Testing note:** Backend tests build the schema from models via `Base.metadata.create_all` (see `backend/tests/conftest.py:38`), so they never exercise the migration. The migration is verified separately in Task 2 against the dev database. Frontend e2e must run through `./scripts/test-e2e.sh`, never bare `npx playwright test`.

---

### Task 1: Require a persona when reading and writing templates

**Files:**
- Modify: `backend/app/writing_template_models.py`
- Modify: `backend/app/writing_template_schemas.py`
- Modify: `backend/app/routers/writing_templates.py:54-85`
- Test: `backend/tests/test_writing_templates.py`

- [ ] **Step 1: Write the failing tests**

Replace the `template_body` helper and add a persona fixture at the top of `backend/tests/test_writing_templates.py`:

```python
from app.db import Session
from app.models import Workspace, Persona
from app.writing_template_models import WritingTemplate


def make_persona(client, label="Finance"):
    return client.post("/api/personas", json={"label": label, "data": {}}).json()["id"]


def template_body(persona_id, **overrides):
    return {
        "persona_id": persona_id,
        "name": "A reusable introduction",
        "description": "For new conversations",
        "subject": "Hello {{name}}",
        "body_html": "<p>Hi {{name}},</p><p>Could we talk about {{company}}?</p>",
        **overrides,
    }
```

Append these new tests to the same file:

```python
def test_templates_are_scoped_to_one_persona(client):
    first, second = make_persona(client, "Finance"), make_persona(client, "Academic")
    saved = client.post("/api/writing-templates", json=template_body(first)).json()

    listed = client.get("/api/writing-templates", params={"persona_id": first}).json()
    assert saved["id"] in [item["id"] for item in listed]

    other = client.get("/api/writing-templates", params={"persona_id": second}).json()
    assert saved["id"] not in [item["id"] for item in other]
    # The three code-constant starters stay visible under every persona.
    assert [item["id"] for item in other] == [
        "default-networking", "default-interview", "default-followup"
    ]


def test_template_requires_a_persona_the_caller_owns(client):
    persona = make_persona(client)
    no_persona = {k: v for k, v in template_body(persona).items() if k != "persona_id"}
    assert client.post("/api/writing-templates", json=no_persona).status_code == 422
    assert client.get("/api/writing-templates").status_code == 422

    with Session() as db:
        db.add(Workspace(id="other-persona-ws", name="Other"))
        db.flush()
        foreign = Persona(workspace_id="other-persona-ws", label="Theirs", data={})
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.post("/api/writing-templates", json=template_body(foreign_id)).status_code == 404
    assert client.get("/api/writing-templates", params={"persona_id": foreign_id}).status_code == 404


def test_deleting_a_persona_deletes_its_templates(client):
    persona = make_persona(client)
    saved = client.post("/api/writing-templates", json=template_body(persona)).json()
    with Session() as db:
        db.delete(db.get(Persona, persona))
        db.commit()
        assert db.get(WritingTemplate, saved["id"]) is None
```

Then update every existing call in that file to pass a persona: in
`test_template_library_persists_sanitizes_and_rejects_stale_updates`,
`test_template_validation_and_workspace_boundaries` and
`test_saved_template_can_be_reused_without_ai_or_contact`, start the test with
`persona = make_persona(client)` and change `template_body(...)` to
`template_body(persona, ...)` and every bare
`client.get("/api/writing-templates")` to
`client.get("/api/writing-templates", params={"persona_id": persona})`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_writing_templates.py -q
```

Expected: FAIL. `test_template_requires_a_persona_the_caller_owns` fails because
the unfiltered `GET` still returns 200, and the others fail with a Pydantic
error about the unexpected `persona_id` field.

- [ ] **Step 3: Add the column to the model**

Replace the imports and class head in `backend/app/writing_template_models.py`:

```python
"""Reusable email content, separate from sequence step templates."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Scoped


class WritingTemplate(Scoped, Base):
    __tablename__ = "writing_templates"

    persona_id: Mapped[str] = mapped_column(
        ForeignKey("personas.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
```

Leave the remaining columns (`description`, `category`, `subject`, `body_html`,
`revision`) exactly as they are.

- [ ] **Step 4: Add the field to the input schema**

In `backend/app/writing_template_schemas.py`, add as the first field of
`WritingTemplateInput`:

```python
    persona_id: str = Field(min_length=1, max_length=64)
```

- [ ] **Step 5: Scope the routes**

In `backend/app/routers/writing_templates.py`, add `Persona` to the model
imports, then replace the `templates` and `create` handlers:

```python
def owned_persona(repo, persona_id):
    """404s when the persona is missing or belongs to another workspace."""
    return repo.get(Persona, persona_id)


@router.get("/writing-templates")
def templates(persona_id: str, repo=Depends(get_repo)):
    owned_persona(repo, persona_id)
    custom = sorted(
        repo.all(WritingTemplate, WritingTemplate.persona_id == persona_id),
        key=lambda x: x.updated_at,
        reverse=True,
    )
    return [{**item, "revision": 1, "is_default": True} for item in DEFAULT_TEMPLATES] + [
        response(item) for item in custom
    ]


@router.post("/writing-templates", status_code=201)
def create(body: WritingTemplateInput, repo=Depends(get_repo)):
    owned_persona(repo, body.persona_id)
    return response(repo.add(WritingTemplate, **values(body)))
```

In `update`, add the same guard as the first line of the handler body:

```python
    owned_persona(repo, body.persona_id)
```

`values(body)` already returns `body.model_dump(exclude={"revision"})`, so
`persona_id` flows into both create and update without further change.

`delete` needs no edit: it resolves the row through `repo.get`, which already
filters by `workspace_id`, so a template in another workspace 404s today and
will continue to.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_writing_templates.py -q
```

Expected: PASS, 6 tests.

- [ ] **Step 7: Run the whole backend suite**

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest -q
```

Expected: PASS. If `tests/test_workflow.py` or `tests/test_export.py` create
templates, give them a persona the same way.

- [ ] **Step 8: Commit**

```bash
git add backend/app/writing_template_models.py backend/app/writing_template_schemas.py backend/app/routers/writing_templates.py backend/tests/test_writing_templates.py
git commit -m "Scope writing templates to a persona"
```

---

### Task 2: Migrate existing templates onto a persona

**Files:**
- Create: `backend/alembic/versions/h631fd751013_persona_owned_templates.py`

- [ ] **Step 1: Write the migration**

Current head is `g531ec641012`. Create the file with this content:

```python
"""Writing templates belong to a persona."""

from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "h631fd751013"
down_revision = "g531ec641012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("writing_templates", sa.Column("persona_id", sa.String(), nullable=True))
    op.create_index("ix_writing_templates_persona_id", "writing_templates", ["persona_id"])
    op.create_foreign_key(
        "fk_writing_templates_persona_id", "writing_templates", "personas",
        ["persona_id"], ["id"], ondelete="CASCADE",
    )
    bind = op.get_bind()
    workspaces = bind.execute(sa.text(
        "select distinct workspace_id from writing_templates"
    )).scalars().all()
    for workspace_id in workspaces:
        persona_id = bind.execute(sa.text(
            "select id from personas where workspace_id = :w"
            " order by created_at asc limit 1"
        ), {"w": workspace_id}).scalar()
        if persona_id is None:
            # Templates must not be lost; an empty persona is recoverable.
            persona_id = str(uuid4())
            bind.execute(sa.text(
                "insert into personas (id, workspace_id, label, domain, version, data,"
                " created_at, updated_at)"
                " values (:i, :w, 'Persona 1', 'finance', 1, '{}', now(), now())"
            ), {"i": persona_id, "w": workspace_id})
        bind.execute(sa.text(
            "update writing_templates set persona_id = :p"
            " where workspace_id = :w and persona_id is null"
        ), {"p": persona_id, "w": workspace_id})
    op.alter_column("writing_templates", "persona_id", nullable=False)


def downgrade():
    op.drop_constraint("fk_writing_templates_persona_id", "writing_templates", type_="foreignkey")
    op.drop_index("ix_writing_templates_persona_id", table_name="writing_templates")
    op.drop_column("writing_templates", "persona_id")
```

- [ ] **Step 2: Record the pre-migration state**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from sqlalchemy import text
from app.db import engine
with engine.connect() as c:
    print('templates:', c.execute(text('select count(*) from writing_templates')).scalar())
    print('personas :', c.execute(text('select count(*) from personas')).scalar())
"
```

Expected on the current dev database: `templates: 2`, `personas: 1`.

- [ ] **Step 3: Run the migration**

```bash
cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head
```

Expected: no error, and the final `alter_column` succeeds, which proves no row
was left without a persona.

- [ ] **Step 4: Verify the backfill**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from sqlalchemy import text
from app.db import engine
with engine.connect() as c:
    print(c.execute(text('select count(*) from writing_templates where persona_id is null')).scalar(), 'orphans (want 0)')
    for r in c.execute(text('select t.name, p.label from writing_templates t join personas p on p.id = t.persona_id')):
        print(' ', r[0], '->', r[1])
"
```

Expected: `0 orphans`, and both templates mapped to `Investment banking · Demo`.

- [ ] **Step 5: Verify the downgrade round-trips**

```bash
cd backend && PYTHONPATH=. .venv/bin/alembic downgrade -1 && PYTHONPATH=. .venv/bin/alembic upgrade head
```

Expected: both commands succeed, and re-running Step 4 still reports `0 orphans`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/h631fd751013_persona_owned_templates.py
git commit -m "Backfill writing templates onto their workspace's first persona"
```

---

### Task 3: Give the template library a persona and a manage-only mode

**Files:**
- Modify: `frontend/components/writing-template-library.tsx`

**Context you need before editing.** This component is not a generic manager —
it is built around applying a template to an open draft. Its current signature
(line 22) is:

```tsx
export default function WritingTemplateLibrary({
  draft, disabled, flush, onApply, bodyOnly = false,
}: {
  draft?: Draft;
  disabled: boolean;
  flush?: () => Promise<Draft | null>;
  onApply: (content: TemplateContent) => Promise<void>;
  bodyOnly?: boolean;
})
```

`saveTemplate` already bails when `flush` is absent (line 114), because saving
means "capture what is in the draft right now". The Personas tab has no draft,
so it gets browse, upload and delete — authoring keeps happening in Email
Studio, where a real email exists to capture. This is deliberate; part B adds
paste-authoring to the tab.

It is a **default export**. Import it without braces.

- [ ] **Step 1: Widen the signature**

```tsx
export default function WritingTemplateLibrary({
  personaId,
  draft,
  disabled,
  flush,
  onApply,
  bodyOnly = false,
}: {
  personaId: string;
  draft?: Draft;
  disabled: boolean;
  flush?: () => Promise<Draft | null>;
  onApply?: (content: TemplateContent) => Promise<void>;
  bodyOnly?: boolean;
}) {
```

- [ ] **Step 2: Scope the fetch to the persona**

Inside `reload`, replace the fetch and skip it entirely without a persona, so
Email Studio drafts with no persona selected show only the three constants:

```tsx
      const items = personaId
        ? await api<WritingTemplate[]>(
            "/writing-templates?persona_id=" + encodeURIComponent(personaId),
          )
        : [];
```

Add `personaId` to `reload`'s `useCallback` dependency array so switching
persona refetches.

- [ ] **Step 3: Send the persona on every write**

In `saveTemplate`, add `personaId` to the guard and the body:

```tsx
    if (
      !flush ||
      !personaId ||
      !name.trim() ||
      (update && (!selected || selected.is_default))
    )
      return;
```

```tsx
      const body = {
        persona_id: personaId,
        name: name.trim(),
        description,
        category: update ? selected!.category : "Custom",
        subject: current.subject,
        body_html: current.body_html,
        ...(update ? { revision: selected!.revision } : {}),
      };
```

In `upload(file)` (line 157), add `persona_id: personaId` to the object posted
to `/writing-templates`.

- [ ] **Step 4: Hide apply-only controls in manage mode**

Wrap the "Use template" button so it renders only when `onApply` is supplied:

```tsx
{onApply && (
  /* existing Use template button, unchanged */
)}
```

Wrap the save controls so they render only when `flush` is supplied. Both
guards are what make the component safe to mount without a draft.

- [ ] **Step 5: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: two errors, both "Property 'personaId' is missing" — at
`writing-templates-page.tsx:49` and `email-studio.tsx:534`. The first file is
deleted in Task 4; the second is fixed in Task 6.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/writing-template-library.tsx
git commit -m "Scope the template library to a persona and allow manage-only use"
```

---

### Task 4: Put the library in a Personas tab and delete the standalone page

**Files:**
- Modify: `frontend/components/personas.tsx`
- Modify: `frontend/app/globals.css`
- Delete: `frontend/components/writing-templates-page.tsx`

- [ ] **Step 1: Add the tab state and markup**

`Personas` is a default export at line 77 and already holds
`const [selected, setSelected] = useState<Persona | null>(...)` at line 89;
`selected?.id` is the persona to pass down. Its `<Heading title="Personas">`
is at line 300.

Import the library (default import — no braces) and add tab state alongside
the existing state:

```tsx
import WritingTemplateLibrary from "./writing-template-library";

const [tab, setTab] = useState<"background" | "templates">("background");
```

Render the switcher directly under the page heading, and the panel below it:

```tsx
<div className="persona-tabs" role="tablist">
  {(["background", "templates"] as const).map((key) => (
    <button
      key={key}
      role="tab"
      type="button"
      aria-selected={tab === key}
      className={tab === key ? "active" : ""}
      onClick={() => setTab(key)}
    >
      {key === "background"
        ? t("Background", "背景")
        : t("Templates", "模板")}
    </button>
  ))}
</div>
```

Wrap the existing persona form so it renders only when `tab === "background"`.
Render the Templates panel otherwise, in manage mode — no `onApply`, no
`flush`, so the library shows browse, upload and delete only:

```tsx
{tab === "templates" &&
  (selected ? (
    <WritingTemplateLibrary personaId={selected.id} disabled={saving} />
  ) : (
    <Empty
      title={t("No persona selected", "尚未选择画像")}
      detail={t(
        "Create or choose a persona before adding templates to it.",
        "请先创建或选择一个画像，再为它添加模板。",
      )}
    />
  ))}
```

`Empty` is already exported from `./ui`; add it to the existing import from
that module if it is not there.

- [ ] **Step 2: Style the tabs**

Append to `frontend/app/globals.css`:

```css
.persona-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
}
.persona-tabs button {
  border: 0;
  background: none;
  padding: 10px 14px;
  font: inherit;
  font-size: 14px;
  color: var(--text-tertiary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.persona-tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
```

- [ ] **Step 3: Delete the standalone page**

```bash
git rm frontend/components/writing-templates-page.tsx
```

- [ ] **Step 4: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: the only remaining error is the unresolved import of
`writing-templates-page` in `workspace.tsx`, fixed in Task 5.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/personas.tsx frontend/app/globals.css
git commit -m "Move the template library into a Personas tab"
```

---

### Task 5: Remove the Templates section

**Files:**
- Modify: `frontend/components/workspace.tsx`

- [ ] **Step 1: Remove the nav entry, import and route**

Delete the `WritingTemplatesPage` import, remove the `["/templates", ...]`
entry from the nav array, and delete the
`) : path === "/templates" ? (` branch together with its rendered component
from the route chain around line 302.

- [ ] **Step 2: Confirm nothing else references the path**

```bash
grep -rn '"/templates"' frontend/ --include=*.tsx --include=*.ts
```

Expected: no matches outside `frontend/tests/`, which Task 7 updates.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/workspace.tsx
git commit -m "Remove the top-level Templates section"
```

---

### Task 6: Gate template saving in Email Studio

**Files:**
- Modify: `frontend/components/email-studio.tsx`

- [ ] **Step 1: Pass the draft's persona to the library**

The render site is `frontend/components/email-studio.tsx:534`. Add one prop,
leaving the existing `draft`, `disabled`, `flush`, `bodyOnly` and `onApply`
props exactly as they are:

```tsx
            <WritingTemplateLibrary
              personaId={draft.persona_id || ""}
              draft={
```

- [ ] **Step 2: Explain why saving is unavailable**

Task 3 Step 3 already blocks the save; this step tells the user why. In
`frontend/components/writing-template-library.tsx`, render the reason inside
the save controls block, and add `|| !personaId` to the save button's
`disabled` expression:

```tsx
{!personaId && (
  <p className="panel-note">
    {t(
      "Choose a persona for this draft before saving a template.",
      "请先为这封草稿选择画像，然后再保存模板。",
    )}
  </p>
)}
```

- [ ] **Step 3: Verify in the browser**

Start the stack if it is not running, open Email Studio, create a draft with no
persona, switch to Template mode.

Expected: three starter templates listed, save button disabled, the reason
visible. Selecting a persona in the draft enables saving.

- [ ] **Step 4: Typecheck and format**

```bash
cd frontend && npx tsc --noEmit && npx prettier --check components/ app/globals.css
```

Expected: exit 0 for both.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/email-studio.tsx frontend/components/writing-template-library.tsx
git commit -m "Require a persona before saving a draft as a template"
```

---

### Task 7: Update the e2e tests

**Files:**
- Modify: `frontend/tests/writing.spec.ts:431`
- Modify: `frontend/tests/workflow.spec.ts:150`

- [ ] **Step 1: Point the template test at the new location**

`writing.spec.ts:431` ("email templates upload, persist across drafts, and
resolve in a real preview") drives the library from Email Studio's Template
mode. That entry point still exists, so the test needs the draft to have a
persona before it can save. Add a persona selection immediately after the draft
is created, before the first `Save as template` click, using the existing
persona `<select>` in the draft form.

- [ ] **Step 2: Drop the /templates assertion**

In `workflow.spec.ts:150` ("resume upload, rich text, independent writing
language and future routes"), remove `/templates` from the list of future
routes it visits, along with any assertion on that page's heading.

- [ ] **Step 3: Cover the persona gate**

Add to `frontend/tests/writing.spec.ts`:

```ts
test("saving a template requires the draft to have a persona", async ({
  page,
}) => {
  await createDraft(page);
  await page.getByRole("button", { name: "Template", exact: true }).click();
  // No persona on a fresh draft: only the three code-constant starters.
  await expect(page.locator(".email-template-list > button")).toHaveCount(3);
  await expect(
    page.getByText("Choose a persona for this draft before saving a template."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save as template", exact: true }),
  ).toBeDisabled();
});
```

If the save button's accessible name differs, read it from
`writing-template-library.tsx` rather than guessing.

- [ ] **Step 4: Run the affected specs in the isolated harness**

```bash
./scripts/test-e2e.sh tests/workflow.spec.ts tests/writing.spec.ts
```

Expected: all pass.

- [ ] **Step 5: Run the full relevant suite**

```bash
./scripts/test-e2e.sh tests/workflow.spec.ts tests/writing.spec.ts tests/people-pagination.spec.ts tests/people-state.spec.ts
```

Expected: 19 passed.

- [ ] **Step 6: Run the backend suite once more**

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

```bash
git add frontend/tests/writing.spec.ts frontend/tests/workflow.spec.ts
git commit -m "Update e2e tests for persona-owned templates"
git push origin main
```
