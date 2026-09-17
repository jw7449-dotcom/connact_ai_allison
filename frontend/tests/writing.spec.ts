import { test, expect, type Page } from "@playwright/test";
import type { Draft, Generation } from "../lib/types";

// Deterministic browser race tests, independent of paid AI providers.
async function writingFixture(page: Page) {
  const drafts: Record<string, Draft> = {},
    jobs: Record<string, Generation[]> = {};
  let sequence = 0,
    failSave = false,
    delaySave = false;
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname.replace(/^\/api/, ""),
      method = req.method();
    const reply = (json: unknown, status = 200) =>
      route.fulfill({ json, status });
    if (path === "/auth/session")
      return reply({
        mode: "local",
        authenticated: true,
        workspace_id: "writing-test",
        email: null,
      });
    if (path === "/config")
      return reply({
        auth_mode: "local",
        people_mode: "mock",
        ai_mode: "mock",
        public_search_mode: "mock",
        providers: {},
      });
    if (path === "/personas" || path === "/contacts") return reply([]);
    if (path === "/mailboxes")
      return reply({ configured: false, mailboxes: [], callback_uri: "" });
    if (path === "/writing-templates") return reply([]);
    if (path === "/ai/models")
      return reply({
        mode: "mock",
        provider: "test",
        configured: true,
        default_model: "qwen-plus",
        models: [
          { id: "qwen-plus", label: "Qwen Plus" },
          { id: "qwen-turbo", label: "Qwen Turbo" },
          {
            id: "deepseek/deepseek-v4-flash",
            label: "DeepSeek V4 Flash",
            provider_label: "DeepSeek",
            available: true,
          },
          {
            id: "openai/gpt-4.1-mini",
            label: "GPT-4.1 mini",
            provider_label: "OpenAI",
            available: false,
          },
        ],
      });
    if (path === "/drafts") {
      if (method === "GET") return reply(Object.values(drafts));
      const id = "writing-" + ++sequence;
      drafts[id] = {
        id,
        contact_id: null,
        persona_id: null,
        persona_version: null,
        language: "en",
        purpose: "",
        starting_point: "Networking",
        writing_mode: "assisted",
        tone: "professional",
        length: "medium",
        cta: "",
        model: "",
        custom_instructions: "",
        evidence_ids: [],
        subject: "",
        body_html: "",
        status: "draft",
        revision: 1,
        updated_at: "2026-09-08T01:00:00Z",
        generation_provider: "",
      };
      return reply(drafts[id]);
    }
    const match = path.match(
      /^\/drafts\/([^/]+)(?:\/generations(?:\/([^/]+)(?:\/(accept|discard))?)?)?$/,
    );
    if (!match)
      return reply({ detail: "Unexpected test endpoint: " + path }, 404);
    const [, id, jobId, action] = match,
      draft = drafts[id];
    if (!draft) return reply({ detail: "Draft not found" }, 404);
    if (!path.includes("/generations")) {
      if (method === "GET") return reply(draft);
      const body = req.postDataJSON() as Draft;
      if (delaySave) {
        delaySave = false;
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
      if (failSave) return route.abort("failed");
      if (body.revision !== drafts[id].revision)
        return reply(
          {
            detail:
              "Draft changed elsewhere. Load the latest version before saving.",
          },
          409,
        );
      drafts[id] = { ...body, id, revision: drafts[id].revision + 1 };
      return reply(drafts[id]);
    }
    jobs[id] ||= [];
    if (!jobId) {
      if (method === "GET") return reply(jobs[id]);
      const body = req.postDataJSON();
      const job: Generation = {
        id: "job-" + ++sequence,
        status: "running",
        draft_revision: body.revision,
        action: body.action,
        model: draft.model || "qwen-plus",
        result: null,
        error: "",
        snapshot: { purpose: draft.purpose, cta: draft.cta },
        created_at: "2026-09-08T01:01:00Z",
      };
      jobs[id].unshift(job);
      return reply(job, 202);
    }
    const job = jobs[id].find((item) => item.id === jobId)!;
    if (action === "discard") {
      job.status = "discarded";
      return reply(job);
    }
    if (action === "accept") {
      if (
        draft.revision !== req.postDataJSON().revision ||
        job.draft_revision !== draft.revision
      )
        return reply(
          {
            detail:
              "Draft changed after generation. Your edits were preserved.",
          },
          409,
        );
      job.status = "accepted";
      drafts[id] = { ...draft, ...job.result, revision: draft.revision + 1 };
      return reply(drafts[id]);
    }
    return reply(job);
  });
  return {
    drafts,
    jobs,
    failSaves: (v: boolean) => {
      failSave = v;
    },
    delayNextSave: () => {
      delaySave = true;
    },
    finish: (id: string) => {
      const job = jobs[id][0];
      job.status = "succeeded";
      job.result = {
        subject: "A thoughtful introduction",
        body_html: "<p>Hello, this is the generated suggestion.</p>",
      };
    },
  };
}
async function createDraft(page: Page) {
  await page.goto("/email");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await expect(page.getByLabel("Subject", { exact: true })).toBeVisible();
  return new URL(page.url()).searchParams.get("draft")!;
}

test("independent brief persists and background suggestions require insertion", async ({
  page,
}) => {
  const fixture = await writingFixture(page),
    id = await createDraft(page);
  await page
    .getByLabel("What would you like to connect about?")
    .fill("Learn about growth investing careers");
  await page
    .getByLabel("Call to action", { exact: true })
    .fill("15-minute conversation next week");
  await page
    .getByLabel("Additional instructions")
    .fill("Keep it specific; avoid clichés.");
  await page.getByLabel("AI model", { exact: true }).selectOption("qwen-turbo");
  await page.getByLabel("Email length").selectOption("short");
  await page.getByLabel("Writing tone").selectOption("warm");
  await page.getByLabel("Subject", { exact: true }).fill("My existing subject");
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill("My existing text remains while AI works.");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toHaveAttribute(
    "data-status",
    "running",
  );
  await expect(
    page.getByRole("textbox", { name: "Email body" }),
  ).toBeEditable();
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "My existing text",
  );
  await expect(page.getByLabel("To · Contact")).toHaveValue("");
  await expect(page.getByLabel("Writing context · Persona")).toHaveValue("");
  await page.getByRole("link", { name: "Contacts", exact: true }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  fixture.finish(id);
  await page.goto("/email?draft=" + id);
  await expect(page.getByLabel("Call to action", { exact: true })).toHaveValue(
    "15-minute conversation next week",
  );
  await expect(page.getByLabel("AI model", { exact: true })).toHaveValue(
    "qwen-turbo",
  );
  await expect(page.getByLabel("Email length")).toHaveValue("short");
  await expect(page.getByLabel("Writing tone")).toHaveValue("warm");
  await expect(page.getByTestId("writing-suggestion")).toHaveAttribute(
    "data-status",
    "succeeded",
  );
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "My existing subject",
  );
  await page
    .getByRole("button", { name: "Insert suggestion", exact: true })
    .click();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "A thoughtful introduction",
  );
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "generated suggestion",
  );
  await page.reload();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "A thoughtful introduction",
  );
  await page.getByRole("button", { name: "Show suggestion history" }).click();
  await expect(page.getByTestId("writing-suggestion")).toHaveAttribute(
    "data-status",
    "accepted",
  );
  expect(fixture.drafts[id].custom_instructions).toBe(
    "Keep it specific; avoid clichés.",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
});

test("edits during generation and another-tab conflicts preserve human text", async ({
  page,
}) => {
  const fixture = await writingFixture(page),
    id = await createDraft(page);
  await page
    .getByLabel("What would you like to connect about?")
    .fill("Explore opportunities");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toBeVisible();
  await page.getByLabel("Subject", { exact: true }).fill("New human subject");
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  fixture.finish(id);
  await page.getByRole("button", { name: "Refresh suggestions" }).click();
  await expect(
    page.getByRole("button", { name: "Insert suggestion", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".writing-stale")).toContainText("draft changed");
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(page.getByTestId("writing-suggestion")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toHaveAttribute(
    "data-status",
    "running",
  );
  fixture.finish(id);
  await page.getByRole("button", { name: "Refresh suggestions" }).click();
  await expect(
    page.getByRole("button", { name: "Insert suggestion", exact: true }),
  ).toBeEnabled();
  fixture.drafts[id] = {
    ...fixture.drafts[id],
    subject: "Saved by another tab",
    revision: fixture.drafts[id].revision + 1,
  };
  await page
    .getByRole("button", { name: "Insert suggestion", exact: true })
    .click();
  await expect(page.locator(".error-panel[role=alert]")).toContainText(
    "Your edits were preserved",
  );
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "New human subject",
  );
  expect(fixture.drafts[id].subject).toBe("Saved by another tab");
});

test("queued edits stay with their draft and failed saves survive reload", async ({
  page,
}) => {
  const fixture = await writingFixture(page),
    id = await createDraft(page);
  fixture.delayNextSave();
  const request = page.waitForRequest(
    (req) => req.method() === "PUT" && req.url().endsWith("/drafts/" + id),
  );
  await page
    .getByLabel("Subject", { exact: true })
    .fill("First in-flight subject");
  await request;
  await page.evaluate(() =>
    window.dispatchEvent(new Event("beforeunload", { cancelable: true })),
  );
  expect(
    await page.evaluate(
      (draftId) =>
        JSON.parse(
          sessionStorage.getItem("connact-draft-buffer:" + draftId) || "{}",
        ).subject,
      id,
    ),
  ).toBe("First in-flight subject");
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Latest queued subject");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await expect(page).not.toHaveURL(new RegExp("draft=" + id + "$"));
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue("");
  const secondId = new URL(page.url()).searchParams.get("draft")!;
  expect(fixture.drafts[id].subject).toBe("Latest queued subject");
  expect(fixture.drafts[secondId].subject).toBe("");
  fixture.failSaves(true);
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Recover me after reload");
  await expect(page.getByText("Save failed", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Recover me after reload",
  );
  await expect(page.locator(".writing-recovery")).toBeVisible();
  fixture.failSaves(false);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  expect(fixture.drafts[secondId].subject).toBe("Recover me after reload");
  expect(fixture.drafts[id].subject).toBe("Latest queued subject");
});

test("prompt and template modes save independently and do not require a persona or contact", async ({
  page,
}) => {
  const fixture = await writingFixture(page),
    id = await createDraft(page);
  await page.getByRole("button", { name: "Prompt", exact: true }).click();
  await expect(
    page.getByLabel("What would you like to connect about?"),
  ).toHaveCount(0);
  await expect(page.getByLabel("Additional instructions")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Prompt editor", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Ask for advice", exact: true })
    .click();
  await expect(page.getByLabel("Your prompt", { exact: true })).toHaveValue(
    /informational interview/,
  );
  await page
    .getByLabel("Your prompt", { exact: true })
    .fill(
      "Write an introduction asking about equity research, without making up my background.",
    );
  await page.getByText("Preview writing request", { exact: true }).click();
  await expect(page.locator(".email-request-preview")).toContainText(
    "equity research",
  );
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toBeVisible();
  expect(fixture.drafts[id].writing_mode).toBe("prompt");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Prompt", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  fixture.finish(id);
  await page.getByRole("button", { name: "Refresh suggestions" }).click();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await page.getByRole("button", { name: "Template", exact: true }).click();
  await expect(page.getByLabel("Your prompt", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Email template library", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill("Hi {{name}}, I would like to learn about your work at {{company}}.");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toBeVisible();
  expect(fixture.drafts[id].writing_mode).toBe("template");
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "{{company}}",
  );
});

test("email templates upload, persist across drafts, and resolve in a real preview", async ({
  page,
}) => {
  // Actual workspace API, with no AI request or paid-provider call.
  const originalId = await createDraft(page);
  await page.getByRole("button", { name: "Template", exact: true }).click();
  await expect(page.locator(".email-template-list > button")).toHaveCount(3);
  await page.getByRole("button", { name: "Use template", exact: true }).click();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "A quick introduction, {{name}}",
  );
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Research conversation for {{name}}");
  await page
    .getByRole("textbox", { name: "Email body", exact: true })
    .fill("Hi {{name}}, could we discuss your work at {{company}}?");
  await page
    .getByRole("button", { name: "Save email as template", exact: true })
    .click();
  await page
    .getByLabel("Template name", { exact: true })
    .fill("Research conversation reusable");
  await page
    .getByLabel("Template description", { exact: true })
    .fill("A reusable research outreach email");
  await page
    .getByRole("button", { name: "Save new template", exact: true })
    .click();
  await expect(
    page
      .locator(".email-template-list > button")
      .filter({ hasText: "Research conversation reusable" }),
  ).toBeVisible();

  await page.reload();
  await expect(
    page
      .locator(".email-template-list > button")
      .filter({ hasText: "Research conversation reusable" }),
  ).toBeVisible();
  const secondId = await createDraft(page);
  expect(secondId).not.toBe(originalId);
  await page.getByRole("button", { name: "Template", exact: true }).click();
  await page
    .getByLabel("Template collection", { exact: true })
    .selectOption("saved");
  await page
    .locator(".email-template-list > button")
    .filter({ hasText: "Research conversation reusable" })
    .click();
  await page.getByRole("button", { name: "Use template", exact: true }).click();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Research conversation for {{name}}",
  );
  const contact = await (
    await page.request.post("/api/contacts", {
      data: { name: "Jordan Template", company: "Example Research" },
    })
  ).json();
  await page.reload();
  await page
    .getByLabel("To · Contact", { exact: true })
    .selectOption(contact.id);
  await page
    .getByRole("button", { name: "Preview & copy", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Research conversation for Jordan Template",
  );
  await expect(page.getByRole("dialog")).toContainText("Example Research");
  await page
    .getByRole("button", { name: "Close details", exact: true })
    .click();

  await page
    .getByLabel("Upload email template JSON", { exact: true })
    .setInputFiles({
      name: "follow-up.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          name: "Imported follow-up",
          subject: "A short follow-up",
          body_html:
            '<p>Following up, {{name}}.</p><img src=x onerror="alert(1)">',
        }),
      ),
    });
  await expect(
    page
      .locator(".email-template-list > button")
      .filter({ hasText: "Imported follow-up" }),
  ).toBeVisible();
  await expect(page.locator(".email-template-preview img")).toHaveCount(0);
  await page.reload();
  await expect(
    page
      .locator(".email-template-list > button")
      .filter({ hasText: "Imported follow-up" }),
  ).toBeVisible();
  await page
    .getByLabel("Upload email template JSON", { exact: true })
    .setInputFiles({
      name: "broken.json",
      mimeType: "application/json",
      buffer: Buffer.from("not JSON"),
    });
  await expect(
    page
      .getByRole("region", { name: "Email template library" })
      .getByRole("alert"),
  ).toContainText("not valid JSON");
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Research conversation for {{name}}",
  );
  await page.goto("/templates");
  await expect(
    page.getByRole("heading", { name: "Email templates", exact: true }),
  ).toBeVisible();
  await page
    .locator(".email-template-list > button")
    .filter({ hasText: "Imported follow-up" })
    .click();
  await page
    .getByRole("button", { name: "Create draft from template", exact: true })
    .click();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "A short follow-up",
  );
  await expect(
    page.getByRole("textbox", { name: "Email body", exact: true }),
  ).toContainText("Following up, {{name}}.");
});

test("provider groups disable missing keys and persist the selected route", async ({
  page,
}) => {
  await writingFixture(page);
  const id = await createDraft(page);
  const select = page.getByLabel("AI model", { exact: true });
  await expect(select.locator('optgroup[label="DeepSeek"]')).toHaveCount(1);
  await expect(
    select.locator('option[value="openai/gpt-4.1-mini"]'),
  ).toBeDisabled();
  await expect(
    select.locator('option[value="openai/gpt-4.1-mini"]'),
  ).toContainText("Not configured");
  await select.selectOption("deepseek/deepseek-v4-flash");
  await page
    .getByLabel("What would you like to connect about?")
    .fill("Career advice");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion")).toContainText(
    "deepseek/deepseek-v4-flash",
  );
  await page.goto("/email?draft=" + id);
  await expect(select).toHaveValue("deepseek/deepseek-v4-flash");
});

test("Bailian models share a platform group and complete a saved writing task", async ({
  page,
}) => {
  // Real backend catalog + persistent worker, with AI_MODE=mock in the isolated stack.
  const id = await createDraft(page);
  const select = page.getByLabel("AI model", { exact: true });
  const group = select.locator('optgroup[label="Bailian MaaS · 百炼多厂商"]');
  await expect(group.locator('option[value="bailian/kimi-k3"]')).toBeEnabled();
  await expect(group.locator('option[value="bailian/glm-5.2"]')).toBeEnabled();
  await expect(
    group.locator('option[value="bailian/MiniMax-M2.5"]'),
  ).toBeEnabled();
  await select.selectOption("bailian/kimi-k3");
  await page
    .getByLabel("What would you like to connect about?")
    .fill("Learn about finance careers");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await expect(page.getByTestId("writing-suggestion").first()).toHaveAttribute(
    "data-status",
    "succeeded",
  );
  await expect(page.getByTestId("writing-suggestion").first()).toContainText(
    "bailian/kimi-k3",
  );
  await page.goto("/email?draft=" + id);
  await expect(select).toHaveValue("bailian/kimi-k3");
});
