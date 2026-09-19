import { test, expect } from "@playwright/test";

test("persona → search → source-based recommendation → contact → edited, autosaved draft → preview and copy", async ({
  page,
}) => {
  const suffix = Date.now().toString().slice(-6);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/personas");
  await page.getByRole("button", { name: "New persona", exact: true }).click();
  await page
    .getByLabel("Persona name", { exact: true })
    .fill("UI test " + suffix);
  await page.getByLabel("Full name", { exact: true }).fill("Taylor Browser");
  await page
    .getByLabel("Finance focus", { exact: true })
    .fill("Investment Banking");
  await page
    .getByLabel("Target organizations or roles", { exact: true })
    .fill("Investment Banking Analyst");
  await page.getByLabel("Target regions", { exact: true }).fill("New York");
  await page.getByRole("button", { name: "Save persona", exact: true }).click();
  await expect(
    page.getByText(
      "Persona saved. A versioned snapshot is ready for personalization.",
    ),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: new RegExp("UI test " + suffix) })
    .click();
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue(
    "Taylor Browser",
  );
  await page.getByLabel("Skills", { exact: true }).fill("Financial modeling");
  await page.getByRole("button", { name: "Save persona", exact: true }).click();
  await expect(page.getByText("Version 2", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "People Search", exact: true }).click();
  await page
    .getByLabel("Recommend for persona", { exact: true })
    .selectOption({ label: "UI test " + suffix });
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  await expect(page.getByText("16 people found")).toBeVisible();
  await expect(page.getByText("MOCK · FICTIONAL").first()).toBeVisible();
  await page.getByRole("button", { name: "Recommend first 5" }).click();
  await expect(page.locator(".match-reason").first()).toContainText(
    "Investment Banking Analyst",
  );
  const row = page.locator("tbody tr").nth(3);
  await row.getByRole("button", { name: /^Sav(e|ed) Ethan Brooks$/ }).click();
  await expect(
    row.getByRole("button", { name: "Saved Ethan Brooks", exact: true }),
  ).toBeVisible();
  await row
    .getByRole("button", { name: "Saved Ethan Brooks", exact: true })
    .click();
  await expect(
    page.getByText("Already saved. No duplicate created."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Contacts", exact: true }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Ethan Brooks Portfolio Manager/ }),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: /Ethan Brooks Portfolio Manager/ })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Fictional demo profile", { exact: true }),
  ).toBeVisible();
  await dialog
    .getByLabel("Recommendation persona")
    .selectOption({ label: "UI test " + suffix });
  await dialog
    .getByRole("button", { name: "Write email", exact: true })
    .click();
  await expect(page.getByLabel("To · Contact")).toHaveValue(/.+/);
  await page
    .getByLabel("What would you like to connect about?")
    .fill("learn about portfolio management careers");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Insert suggestion", exact: true })
    .click();
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "{{sender_name}}",
  );
  await page
    .getByLabel("Subject", { exact: true })
    .fill("A conversation with {{name}} · " + suffix);
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill(
      "Dear {{name}},\nThank you for sharing your perspective at {{company}}.\nBest, {{sender_name}}",
    );
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  const url = page.url();
  await page.reload();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "A conversation with {{name}} · " + suffix,
  );
  await page
    .getByRole("button", { name: "Preview & copy", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByRole("heading", {
      name: "A conversation with Ethan Brooks · " + suffix,
    }),
  ).toBeVisible();
  await expect(page.locator(".preview-body")).toContainText("Taylor Browser");
  await page.getByRole("button", { name: "Copy all", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toContain("Ethan Brooks");
  await page
    .getByRole("button", { name: "Mark as reviewed & ready", exact: true })
    .click();
  await expect(page.locator(".composer-footer")).toContainText("Reviewed");
  await page.getByLabel("Interface language").selectOption("zh");
  await expect(
    page.getByRole("heading", { name: "邮件工作室", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Email language")).toHaveValue("en");
  await page.getByLabel("Interface language").selectOption("en");
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill("Hello {{name}}, your school is {{school}}. Unknown: {{missing}}");
  await page
    .getByRole("button", { name: "Preview & copy", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Missing variables");
  await expect(
    page.getByRole("button", { name: "Mark as reviewed & ready", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Close details" }).click();
  await page.goto("/academic");
  await expect(page.getByText("Coming Soon", { exact: true })).toBeVisible();
  await expect(page.getByRole("main").getByRole("button")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("resume upload, rich text, independent writing language and future routes", async ({
  page,
}) => {
  await page.goto("/personas");
  await page.getByRole("button", { name: "New persona", exact: true }).click();
  await page
    .getByLabel("Upload resume", { exact: true })
    .setInputFiles("../demo/sample-resume.docx");
  await page
    .getByRole("button", { name: "Use parsed fields", exact: true })
    .click();
  await expect(page.getByLabel("Full name", { exact: true })).toHaveValue(
    "Alex Morgan",
  );
  await expect(page.getByLabel("Education", { exact: true })).toHaveValue(
    /New York University/,
  );
  await page
    .getByLabel("Persona name", { exact: true })
    .fill("Uploaded demo " + Date.now());
  await page.getByRole("button", { name: "Save persona", exact: true }).click();
  await expect(
    page.getByText(
      "Persona saved. A versioned snapshot is ready for personalization.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "New persona", exact: true }).click();
  await page
    .getByLabel("Upload resume", { exact: true })
    .setInputFiles("../demo/image-only.pdf");
  await expect(page.locator(".error-panel")).toContainText(
    "Scanned/image-only resumes are unsupported",
  );
  await page.goto("/email");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await page
    .getByLabel("What would you like to connect about?")
    .fill("了解行业经验");
  await page.getByLabel("Email language").selectOption("zh");
  await page
    .getByRole("button", { name: "Generate email", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Insert suggestion", exact: true })
    .click();
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "您好",
  );
  await page.getByRole("textbox", { name: "Email body" }).click();
  await page
    .getByRole("textbox", { name: "Email body" })
    .press("ControlOrMeta+End");
  await page.getByRole("button", { name: "Bold", exact: true }).click();
  await page.keyboard.type("bold text");
  await expect(page.locator(".email-content strong")).toContainText(
    "bold text",
  );
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await page.reload();
  await expect(page.locator(".email-content strong")).toContainText(
    "bold text",
  );
  await page.goto("/templates");
  await expect(
    page.getByRole("region", { name: "Email template library" }),
  ).toBeVisible();
  for (const route of ["campaigns", "analytics", "settings"]) {
    await page.goto("/" + route);
    await expect(page.getByText("Coming Soon", { exact: true })).toBeVisible();
  }
  for (const [route, title] of [
    ["mailboxes", "Mailboxes"],
    ["inbox", "Inbox"],
    ["outbox", "Outbox"],
    ["followups", "Follow-ups"],
  ]) {
    await page.goto("/" + route);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Coming Soon", { exact: true })).toHaveCount(0);
  }
  await page.goto("/settings/integrations");
  await expect(
    page.getByRole("link", { name: "Manage Gmail", exact: true }),
  ).toBeVisible();
});

test("dashboard layout renders without horizontal page overflow", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.screenshot({ path: "../docs/dashboard.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({ path: "../docs/mobile.png", fullPage: true });
});

test("autosave queues rapid edits and preserves the buffer after a network failure", async ({
  page,
}) => {
  await page.goto("/email");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await expect(page.getByLabel("Subject", { exact: true })).toBeVisible();
  const url = page.url();
  let delayed = false;
  await page.route("**/api/drafts/*", async (route) => {
    if (route.request().method() === "PUT" && !delayed) {
      delayed = true;
      await new Promise((resolve) => setTimeout(resolve, 900));
    }
    await route.continue();
  });
  const started = page.waitForRequest(
    (req) => req.method() === "PUT" && req.url().includes("/api/drafts/"),
  );
  await page.getByLabel("Subject", { exact: true }).fill("First version");
  await started;
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Latest queued version");
  await page
    .getByRole("textbox", { name: "Email body" })
    .fill("The latest body survives navigation.");
  await page.getByRole("link", { name: "Contacts", exact: true }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await page.goto(url);
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Latest queued version",
  );
  await expect(page.getByRole("textbox", { name: "Email body" })).toContainText(
    "The latest body survives navigation.",
  );
  await page.unroute("**/api/drafts/*");
  await page.route("**/api/drafts/*", (route) =>
    route.request().method() === "PUT"
      ? route.abort("failed")
      : route.continue(),
  );
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Preserved during outage");
  await expect(page.getByText("Save failed", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Preserved during outage",
  );
  await page.unroute("**/api/drafts/*");
  await page.getByRole("button", { name: "Retry save", exact: true }).click();
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "Preserved during outage",
  );
});
