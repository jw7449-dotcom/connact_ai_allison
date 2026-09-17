import { test, expect, type Page, type APIResponse } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { Draft } from "../lib/types";
import type { Sequence, SequenceTemplate } from "../lib/sequence-types";

// Uses the disposable real Next/FastAPI workspace from scripts/test-e2e.sh.
// No API routes are mocked and no external provider or mailbox is contacted.
async function json<T>(response: APIResponse): Promise<T> {
  expect(
    response.ok(),
    `${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.json();
}
const unique = (name: string) =>
  `${name} ${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const steps = (page: Page) => page.getByTestId("sequence-step");
async function current(page: Page) {
  const id = new URL(page.url()).searchParams.get("sequence");
  expect(id).toBeTruthy();
  return json<Sequence>(await page.request.get(`/api/sequences/${id}`));
}
async function start(page: Page, name: string) {
  await page.goto("/sequences");
  await expect(
    page.getByRole("link", { name: "Sequences", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New sequence", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "Create a sequence",
    exact: true,
  });
  await dialog.getByLabel("Sequence name", { exact: true }).fill(name);
  return dialog;
}
async function openSequence(page: Page, values: object) {
  const sequence = await json<Sequence>(
    await page.request.post("/api/sequences", { data: values }),
  );
  await page.goto(`/sequences?sequence=${sequence.id}`);
  await expect(
    page.getByRole("heading", { name: sequence.name, exact: true }),
  ).toBeVisible();
  return sequence;
}

test.beforeEach(async ({ page }) => {
  const config = await json<{ ai_mode: string; people_mode: string }>(
    await page.request.get("/api/config"),
  );
  expect(config.ai_mode).toBe("mock");
  expect(config.people_mode).toBe("mock");
});

for (const preset of [
  {
    name: "Networking",
    titles: ["Introduction", "Gentle follow-up", "Close the loop"],
    days: [0, 4, 7],
  },
  {
    name: "Recruiting",
    titles: ["Express interest", "Ask about the process", "Final follow-up"],
    days: [0, 5, 7],
  },
  {
    name: "Reconnect",
    titles: ["Open a conversation", "Keep the door open"],
    days: [0, 7],
  },
]) {
  test(`default ${preset.name} template creates a persisted connected workflow`, async ({
    page,
  }) => {
    const name = unique(`${preset.name} workflow`);
    const dialog = await start(page, name);
    await expect(
      dialog
        .locator(".sequence-template-picker > button")
        .filter({ hasText: "Default" }),
    ).toHaveCount(3);
    await dialog
      .locator(".sequence-template-picker > button")
      .filter({ has: page.getByText(preset.name, { exact: true }) })
      .click();
    await dialog
      .getByRole("button", { name: "Create sequence", exact: true })
      .click();
    await expect(page).toHaveURL(/\/sequences\?sequence=.+/);
    await expect(steps(page)).toHaveCount(preset.titles.length);
    for (const [index, title] of preset.titles.entries()) {
      await expect(
        steps(page)
          .nth(index)
          .getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
    }
    await expect(
      page.getByRole("button", { name: "Move step 1 up", exact: true }),
    ).toBeDisabled();
    await expect(steps(page).first()).toContainText("Day 1");
    await expect(steps(page).nth(1)).toContainText("Reply in previous thread");
    const saved = await current(page);
    expect(saved.steps.map((step) => step.delay_days)).toEqual(preset.days);
    expect(saved.status).toBe("draft");
    await page.reload();
    await expect(steps(page)).toHaveCount(preset.titles.length);
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  });
}

test("draft sources are independent copies; inline edits, ordering and timing survive reload", async ({
  page,
}) => {
  const original = await json<Draft>(
    await page.request.post("/api/drafts", {
      data: {
        subject: unique("Original saved email"),
        body_html: "<p>Original human text for {{name}}.</p>",
        purpose: "Ask for career advice",
        writing_mode: "template",
      },
    }),
  );
  const name = unique("Draft-based sequence");
  const dialog = await start(page, name);
  await dialog
    .getByRole("button", { name: "From drafts", exact: true })
    .click();
  await dialog
    .getByLabel("Search draft emails", { exact: true })
    .fill(original.subject);
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "Create sequence", exact: true })
    .click();
  await expect(steps(page)).toHaveCount(1);
  let saved = await current(page);
  expect(saved.steps[0].draft_id).not.toBe(original.id);
  expect(saved.steps[0].draft.body_html).toBe(original.body_html);
  await steps(page)
    .first()
    .getByRole("button", { name: "Write email", exact: true })
    .click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Edited inside the sequence");
  await page
    .getByRole("textbox", { name: "Email body", exact: true })
    .fill("A revised invitation to meet next week.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(steps(page).first()).toContainText("Edited inside the sequence");
  const untouched = await json<Draft>(
    await page.request.get(`/api/drafts/${original.id}`),
  );
  expect({
    subject: untouched.subject,
    body: untouched.body_html,
    revision: untouched.revision,
  }).toEqual({
    subject: original.subject,
    body: original.body_html,
    revision: original.revision,
  });

  await page.getByRole("button", { name: "Add a step", exact: true }).click();
  let settings = page.getByRole("dialog", {
    name: "Add an email step",
    exact: true,
  });
  await settings
    .getByLabel("Step title", { exact: true })
    .fill("Reused second draft");
  await settings
    .getByLabel("Wait days after previous step", { exact: true })
    .fill("5");
  await settings
    .getByLabel("Email source", { exact: true })
    .selectOption("draft");
  await settings
    .getByLabel("Search draft emails", { exact: true })
    .fill(original.subject);
  await settings.getByRole("radio").check();
  await settings
    .getByRole("button", { name: "Save step", exact: true })
    .click();
  await expect(steps(page)).toHaveCount(2);
  await expect(steps(page).nth(1)).toContainText("Day 6");
  saved = await current(page);
  expect(new Set(saved.steps.map((step) => step.draft_id)).size).toBe(2);
  expect(saved.steps[1].draft_id).not.toBe(original.id);
  expect(saved.steps[1].draft.subject).toBe(original.subject);

  await page
    .getByRole("button", { name: "Move step 2 up", exact: true })
    .click();
  await expect(steps(page).first()).toContainText("Reused second draft");
  await expect(steps(page).first()).toContainText("Day 1");
  await expect(steps(page).first()).toContainText("New thread");
  await page
    .getByRole("button", { name: "Step 2 settings", exact: true })
    .click();
  settings = page.getByRole("dialog", { name: "Step settings", exact: true });
  await settings
    .getByLabel("Wait days after previous step", { exact: true })
    .fill("9");
  await settings
    .getByLabel("Email thread", { exact: true })
    .selectOption("reply");
  await settings
    .getByRole("button", { name: "Save step", exact: true })
    .click();
  await expect(steps(page).nth(1)).toContainText("Day 10");
  await page.reload();
  saved = await current(page);
  expect(
    saved.steps.map((step) => [step.title, step.delay_days, step.thread_mode]),
  ).toEqual([
    ["Reused second draft", 0, "new_thread"],
    ["Email 1", 9, "reply"],
  ]);
  await expect(steps(page).nth(1)).toContainText(
    "Inherits the previous subject",
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await steps(page)
    .nth(1)
    .getByRole("button", { name: "Write email", exact: true })
    .click();
  await expect(page.getByLabel("Subject", { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
});

test("context and review gate unresolved recipients, resolve reply threads, and invalidate stale review", async ({
  page,
}) => {
  const contact = await json<{ id: string }>(
    await page.request.post("/api/contacts", {
      data: { name: "Morgan Sequence", company: "Example Capital" },
    }),
  );
  const persona = await json<{ id: string }>(
    await page.request.post("/api/personas", {
      data: {
        label: unique("Sequence sender"),
        data: { name: "Taylor Sender" },
      },
    }),
  );
  await openSequence(page, {
    name: unique("Review sequence"),
    template_id: "default-networking",
  });
  await page.getByRole("button", { name: /Preview & review$/ }).click();
  await expect(
    page.getByRole("button", { name: "Mark sequence reviewed", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".sequence-preview").first()).toContainText(
    "Choose a recipient.",
  );
  await page.getByRole("button", { name: /People & context$/ }).click();
  await page
    .getByLabel("Sequence contact", { exact: true })
    .selectOption(contact.id);
  await page
    .getByLabel("Sequence sender persona", { exact: true })
    .selectOption(persona.id);
  await expect(
    page.getByRole("button", { name: "Next: preview & review", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Apply to all emails", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Next: preview & review", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Next: preview & review", exact: true })
    .click();
  await expect(page.locator(".sequence-preview")).toHaveCount(3);
  await expect(page.locator(".sequence-preview").first()).toContainText(
    "Morgan Sequence",
  );
  await expect(page.locator(".sequence-preview").first()).toContainText(
    "Example Capital",
  );
  await expect(page.locator(".sequence-preview").first()).toContainText(
    "Taylor Sender",
  );
  await expect(
    page.locator(".sequence-preview").nth(1).getByRole("heading"),
  ).toHaveText("Re: A brief introduction");
  await page
    .getByRole("button", { name: "Mark sequence reviewed", exact: true })
    .click();
  await expect(page.locator(".sequence-detail-heading")).toContainText(
    "Reviewed",
  );
  expect((await current(page)).status).toBe("ready");
  await expect(
    page.getByText("Reviewed sequences stay in your workspace.", {
      exact: false,
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: /Build steps$/ }).click();
  await steps(page)
    .first()
    .getByRole("button", { name: "Write email", exact: true })
    .click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("A human revision after review");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".sequence-detail-heading")).toContainText(
    "Draft sequence",
  );
  expect((await current(page)).status).toBe("draft");
});

test("step templates save, download, validate uploads and round-trip into a fresh sequence", async ({
  page,
}) => {
  const sequence = await openSequence(page, {
    name: unique("Reusable plan"),
    template_id: "default-reconnect",
  });
  const templateName = unique("Saved step template");
  await page
    .getByRole("button", { name: "Save as template", exact: true })
    .click();
  await page.getByLabel("Template name", { exact: true }).fill(templateName);
  await page
    .getByRole("button", { name: "Save template", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Step templates", exact: true })
    .click();
  const library = page.getByRole("dialog", {
    name: "Reusable step templates",
    exact: true,
  });
  const savedCard = library.locator(".sequence-library-item").filter({
    has: page.getByRole("heading", { name: templateName, exact: true }),
  });
  await expect(savedCard).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await savedCard
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  const download = await downloadEvent;
  const exported = JSON.parse(
    await readFile((await download.path())!, "utf8"),
  ) as SequenceTemplate;
  expect(exported.schema_version).toBe(1);
  expect(exported.steps).toHaveLength(2);
  expect(exported.steps[1].delay_days).toBe(7);
  expect(exported).not.toHaveProperty("contact_id");
  expect(exported).not.toHaveProperty("persona_id");
  expect(exported.steps[0].body_html).toContain("{{name}}");
  expect(exported.steps[0].body_html).toBe(sequence.steps[0].draft.body_html);

  const importedName = unique("Uploaded step template");
  exported.name = importedName;
  exported.steps[1].delay_days = 12;
  await library
    .getByLabel("Upload step template JSON", { exact: true })
    .setInputFiles({
      name: "invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify({ ...exported, steps: [] })),
    });
  await expect(library.getByRole("alert")).toBeVisible();
  await library
    .getByLabel("Upload step template JSON", { exact: true })
    .setInputFiles({
      name: "roundtrip.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(exported)),
    });
  await expect(
    library.getByRole("heading", { name: importedName, exact: true }),
  ).toBeVisible();
  await expect(library.getByRole("alert")).toHaveCount(0);
  await library
    .getByRole("button", { name: "Close details", exact: true })
    .click();
  await page.reload();
  await page.getByRole("button", { name: "New sequence", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "Create a sequence",
    exact: true,
  });
  await dialog
    .getByLabel("Sequence name", { exact: true })
    .fill(unique("Imported workflow"));
  await dialog
    .locator(".sequence-template-picker > button")
    .filter({ hasText: importedName })
    .click();
  await dialog
    .getByRole("button", { name: "Create sequence", exact: true })
    .click();
  await expect(steps(page)).toHaveCount(2);
  await expect(steps(page).nth(1)).toContainText("Day 13");
  const imported = await current(page);
  expect(imported.id).not.toBe(sequence.id);
  expect(imported.steps.map((step) => step.draft.body_html)).toEqual(
    sequence.steps.map((step) => step.draft.body_html),
  );
  expect(imported.steps[0].draft_id).not.toBe(sequence.steps[0].draft_id);
});

test("AI planning persists progress and Mock attribution after leaving and reopening", async ({
  page,
}) => {
  const dialog = await start(page, unique("AI sequence"));
  await dialog
    .getByRole("button", { name: "Plan with AI", exact: true })
    .click();
  await dialog
    .getByLabel("What should this sequence achieve?", { exact: true })
    .fill(
      "Ask a finance professional for a short career conversation, then follow up respectfully over two weeks.",
    );
  await dialog.getByLabel("Number of steps", { exact: true }).fill("3");
  await expect(dialog).toContainText("Mock AI");
  await dialog
    .getByRole("button", { name: "Create & generate steps", exact: true })
    .click();
  await expect(page).toHaveURL(/\/sequences\?sequence=.+/);
  const url = page.url();
  await page.reload();
  const progress = page.getByTestId("sequence-generation");
  await expect(progress).toHaveAttribute("data-status", "succeeded", {
    timeout: 30000,
  });
  await expect(progress).toContainText("Mock AI");
  await expect(progress).toContainText("3 / 3 steps generated");
  await expect(steps(page)).toHaveCount(3);
  const generated = await current(page);
  expect(generated.generation?.result_steps).toHaveLength(3);
  expect(
    generated.steps.every((step) => step.draft.generation_provider === "mock"),
  ).toBe(true);
  await page.getByRole("link", { name: "All sequences", exact: true }).click();
  await page.goto(url);
  await expect(page.getByTestId("sequence-generation")).toHaveAttribute(
    "data-status",
    "succeeded",
  );
  await expect(steps(page)).toHaveCount(3);
  await page
    .getByRole("button", { name: "AI step settings", exact: true })
    .click();
  const settings = page.getByRole("dialog", {
    name: "AI step settings",
    exact: true,
  });
  await settings
    .getByLabel("Sequence planning prompt", { exact: true })
    .fill("Replace this with two polite career networking steps.");
  await settings.getByLabel("Number of steps", { exact: true }).fill("2");
  await settings
    .getByRole("button", { name: "Generate step plan", exact: true })
    .click();
  await expect(page.getByTestId("sequence-generation")).toContainText(
    "2 / 2 steps generated",
    { timeout: 30000 },
  );
  await expect(steps(page)).toHaveCount(2);
  for (const previous of generated.steps) {
    const preserved = await json<Draft>(
      await page.request.get(`/api/drafts/${previous.draft_id}`),
    );
    expect(preserved.body_html).toBe(previous.draft.body_html);
  }
});
