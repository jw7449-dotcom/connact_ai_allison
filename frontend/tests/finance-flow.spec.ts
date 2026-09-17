import { test, expect, type APIResponse } from "@playwright/test";
import type { Contact, Draft, Persona } from "../lib/types";
import type { Sequence } from "../lib/sequence-types";

// Run with scripts/test-e2e.sh: real Next/FastAPI routes, disposable storage,
// and explicitly verified Mock providers. No external lookup or send is used.
async function json<T>(response: APIResponse): Promise<T> {
  expect(
    response.ok(),
    `${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.json();
}

test("Finance guides a saved persona and contact through one persistent draft, review and follow-up", async ({
  page,
}) => {
  test.setTimeout(90000);
  const config = await json<{ ai_mode: string; people_mode: string }>(
    await page.request.get("/api/config"),
  );
  expect(config.ai_mode).toBe("mock");
  expect(config.people_mode).toBe("mock");
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const personaLabel = `Finance flow ${suffix}`;
  const errors: string[] = [];
  const draftCreations: string[] = [];
  const sequenceCreations: string[] = [];
  const externalActions: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    const path = new URL(request.url()).pathname;
    if (path === "/api/drafts") draftCreations.push(request.postData() || "");
    if (path === "/api/sequences")
      sequenceCreations.push(request.postData() || "");
    if (/\/(email|email_apify|send|activate)(?:\/|$)/.test(path))
      externalActions.push(path);
  });

  await page.goto("/finance");
  const flow = page.getByTestId("finance-flow");
  const navigation = page.getByRole("navigation", {
    name: "Finance workflow steps",
  });
  await expect(flow).toHaveAttribute("data-step", "0");
  await expect(navigation.getByRole("button")).toHaveCount(5);
  for (const href of ["/personas", "/people", "/contacts", "/email"])
    await expect(
      page
        .getByRole("navigation", { name: "Main navigation" })
        .locator(`a[href="${href}"]`),
    ).toBeVisible();

  const personaSelect = page.getByLabel("Workflow persona", { exact: true });
  const closePersonaEditor = page.getByRole("button", {
    name: "Close persona editor",
    exact: true,
  });
  if (await closePersonaEditor.isVisible()) await closePersonaEditor.click();
  await personaSelect.selectOption("");
  await expect(
    page.getByRole("button", { name: "Continue to people", exact: true }),
  ).toBeDisabled();
  const createPersona = page.getByRole("button", {
    name: "Create a persona",
    exact: true,
  });
  await createPersona.click();
  await page.getByLabel("Persona name", { exact: true }).fill(personaLabel);
  await page.getByLabel("Full name", { exact: true }).fill("Taylor Finance");
  await page
    .getByLabel("Finance focus", { exact: true })
    .fill("Investment Banking");
  await page
    .getByLabel("Target organizations or roles", { exact: true })
    .fill("Investment Banking Analyst");
  const personaResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/personas",
  );
  await page.getByRole("button", { name: "Save persona", exact: true }).click();
  const persona: Persona = await (await personaResponse).json();
  await expect(personaSelect).toHaveValue(persona.id);
  await createPersona.click();
  await expect(page.getByLabel("Persona name", { exact: true })).toHaveValue(
    "",
  );
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue("");
  await closePersonaEditor.click();
  await expect(personaSelect).toHaveValue(persona.id);
  await page
    .getByRole("button", { name: "Continue to people", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "1");
  await expect(
    page.getByRole("button", { name: "Continue to writing", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Recommend for persona", { exact: true }),
  ).toHaveValue(persona.id);

  const search = page.getByRole("button", {
    name: "Search people",
    exact: true,
  });
  await expect(search).toBeEnabled();
  for (const label of [
    "Job title",
    "Company / institution",
    "Location",
    "Keywords",
  ])
    await page.getByLabel(label, { exact: true }).fill("");
  await page.getByLabel("Finance focus", { exact: true }).selectOption("");
  await search.click();
  await expect(page.getByText("16 people found")).toBeVisible();
  const firstPerson = page.locator("tbody tr").first();
  const contactName = await firstPerson
    .locator(".person-cell strong")
    .innerText();
  await firstPerson
    .getByRole("button", { name: "Use this contact", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Continue to writing", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "2");
  expect(draftCreations).toHaveLength(1);
  const drafts = await json<Draft[]>(await page.request.get("/api/drafts"));
  const linkedDrafts = drafts.filter(
    (draft) => draft.persona_id === persona.id,
  );
  expect(linkedDrafts).toHaveLength(1);
  const draft = linkedDrafts[0];
  const contact = await json<Contact>(
    await page.request.get(`/api/contacts/${draft.contact_id}`),
  );
  expect(contact.name).toBe(contactName);
  expect(contact.saved).toBe(true);
  expect(draft.persona_version).toBe(persona.version);
  await expect(page.getByLabel("To · Contact", { exact: true })).toHaveValue(
    contact.id,
  );
  await expect(
    page.getByLabel("Writing context · Persona", { exact: true }),
  ).toHaveValue(persona.id);
  await expect(page.getByLabel("To · Contact", { exact: true })).toBeDisabled();
  await expect(
    page.getByLabel("Writing context · Persona", { exact: true }),
  ).toBeDisabled();
  for (const mode of ["Assisted", "Prompt", "Template"])
    await expect(
      page.getByRole("button", { name: mode, exact: true }),
    ).toBeVisible();

  // A failed save must preserve the editor and must not advance the workflow.
  const subject = `Finance introduction to {{name}} ${suffix}`;
  await page.route(`**/api/drafts/${draft.id}`, async (route) => {
    if (route.request().method() === "PUT") return route.abort("failed");
    return route.continue();
  });
  await page.getByLabel("Subject", { exact: true }).fill(subject);
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill(
      "Hello {{name}}, I would appreciate your perspective at {{company}}. Best, {{sender_name}}",
    );
  await page
    .getByRole("button", { name: "Continue to review", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "2");
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    subject,
  );
  await page.unroute(`**/api/drafts/${draft.id}`);
  await page
    .getByRole("button", { name: "Continue to review", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "3");
  const saved = await json<Draft>(
    await page.request.get(`/api/drafts/${draft.id}`),
  );
  expect(saved.subject).toBe(subject);
  expect(saved.body_html).toContain("{{sender_name}}");
  await expect(flow).toContainText(
    `Finance introduction to ${contactName} ${suffix}`,
  );
  await expect(flow).toContainText("Taylor Finance");
  await expect(
    page.getByRole("button", { name: "Continue to follow-up", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Mark as reviewed & ready", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Continue to follow-up", exact: true }),
  ).toBeEnabled();
  expect(
    (await json<Draft>(await page.request.get(`/api/drafts/${draft.id}`)))
      .status,
  ).toBe("ready");
  await page
    .getByRole("button", { name: "Continue to follow-up", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "4");
  const sequenceName = `Finance follow-up ${suffix}`;
  await page.getByLabel("Sequence name", { exact: true }).fill(sequenceName);
  const sequenceResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/sequences",
  );
  await page
    .getByRole("button", { name: "Create follow-up sequence", exact: true })
    .click();
  const sequence: Sequence = await (await sequenceResponse).json();
  expect(sequence.name).toBe(sequenceName);
  expect(sequence.status).toBe("draft");
  expect(sequence.contact_id).toBe(contact.id);
  expect(sequence.persona_id).toBe(persona.id);
  expect(sequence.steps).toHaveLength(2);
  expect(sequence.steps.map((step) => step.delay_days)).toEqual([0, 3]);
  expect(sequence.steps.every((step) => step.draft_id !== draft.id)).toBe(true);
  expect(new Set(sequence.steps.map((step) => step.draft_id)).size).toBe(2);
  expect(
    (await json<Draft>(await page.request.get(`/api/drafts/${draft.id}`)))
      .status,
  ).toBe("ready");
  await expect(
    page.getByRole("link", { name: "Open sequence editor", exact: true }),
  ).toHaveAttribute("href", `/sequences?sequence=${sequence.id}`);
  await page.reload();
  await expect(flow).toHaveAttribute("data-step", "4");
  await expect(
    page.getByRole("link", { name: "Open sequence editor", exact: true }),
  ).toHaveAttribute("href", `/sequences?sequence=${sequence.id}`);
  expect(sequenceCreations).toHaveLength(1);
  await expect(page).toHaveURL(/\/finance$/);

  // Returning to earlier stages keeps the same saved contact and draft.
  await navigation.getByRole("button", { name: /2 People/ }).click();
  await expect(flow).toHaveAttribute("data-step", "1");
  await page
    .getByRole("button", { name: "Continue to writing", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "2");
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    subject,
  );
  expect(draftCreations).toHaveLength(1);

  // Content edits invalidate the previous review, including unresolved variables.
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill("Hello {{unknown_finance_field}}");
  await page
    .getByRole("button", { name: "Continue to review", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "3");
  await expect(flow).toContainText("unknown_finance_field");
  await expect(
    page.getByRole("button", { name: "Mark as reviewed & ready", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Continue to follow-up", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Previous step", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "2");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "People Search", exact: true })
    .click();
  await expect(page).toHaveURL(/\/people$/);
  await expect(
    page.getByRole("heading", { name: "People Search", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Finance", exact: true }).click();
  await expect(flow).toHaveAttribute("data-step", "2");
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    subject,
  );
  expect(draftCreations).toHaveLength(1);
  expect(sequenceCreations).toHaveLength(1);

  // A newer version of the same persona refreshes the writing context without
  // replacing the existing draft or its manually edited subject and body.
  const beforePersonaUpdate = await json<Draft>(
    await page.request.get(`/api/drafts/${draft.id}`),
  );
  const updatedPersona = await json<Persona>(
    await page.request.put(`/api/personas/${persona.id}`, {
      data: {
        label: persona.label,
        version: persona.version,
        data: { ...persona.data, name: "Taylor Updated Finance" },
      },
    }),
  );
  expect(updatedPersona.version).toBe(persona.version + 1);
  await navigation.getByRole("button", { name: /2 People/ }).click();
  await expect(flow).toHaveAttribute("data-step", "1");
  await page
    .getByRole("button", { name: "Continue to writing", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "2");
  const updatedContext = await json<Draft>(
    await page.request.get(`/api/drafts/${draft.id}`),
  );
  expect(updatedContext.persona_version).toBe(updatedPersona.version);
  expect(updatedContext.subject).toBe(beforePersonaUpdate.subject);
  expect(updatedContext.body_html).toBe(beforePersonaUpdate.body_html);
  expect(updatedContext.status).toBe("draft");
  expect(draftCreations).toHaveLength(1);
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    subject,
  );

  // If another editor changes the recipient, retain that independent draft
  // and let the user explicitly continue with a fresh workflow draft.
  const externallyEdited = await json<Draft>(
    await page.request.put(`/api/drafts/${draft.id}`, {
      data: {
        ...updatedContext,
        contact_id: null,
        subject: `Saved outside finance ${suffix}`,
        status: "draft",
      },
    }),
  );
  await navigation.getByRole("button", { name: /2 People/ }).click();
  await expect(flow).toHaveAttribute("data-step", "1");
  await page
    .getByRole("button", { name: "Continue to writing", exact: true })
    .click();
  await expect(flow).toHaveAttribute("data-step", "1");
  await expect(flow.getByRole("alert")).toContainText(
    "The draft context changed elsewhere",
  );
  expect(draftCreations).toHaveLength(1);
  const replacementResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/drafts",
  );
  await page
    .getByRole("button", { name: "Continue to writing", exact: true })
    .click();
  const replacement: Draft = await (await replacementResponse).json();
  await expect(flow).toHaveAttribute("data-step", "2");
  expect(replacement.id).not.toBe(draft.id);
  expect(replacement.contact_id).toBe(contact.id);
  expect(replacement.persona_id).toBe(persona.id);
  expect(replacement.persona_version).toBe(updatedPersona.version);
  expect(draftCreations).toHaveLength(2);
  await expect(page.getByLabel("To · Contact", { exact: true })).toHaveValue(
    contact.id,
  );
  const preserved = await json<Draft>(
    await page.request.get(`/api/drafts/${draft.id}`),
  );
  expect(preserved.contact_id).toBeNull();
  expect(preserved.subject).toBe(externallyEdited.subject);
  expect(preserved.body_html).toBe(externallyEdited.body_html);
  expect(preserved.revision).toBe(externallyEdited.revision);
  expect(sequenceCreations).toHaveLength(1);
  expect(externalActions).toEqual([]);
  expect(errors).toEqual([]);
});
