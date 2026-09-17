import { test, expect, type Page } from "@playwright/test";

const adminSession = {
  mode: "open",
  authenticated: true,
  is_admin: true,
  email: "admin",
  workspace_id: "existing-admin-workspace",
  provider: "password",
  google_configured: true,
  google_linked: false,
};

async function mockAdmin(page: Page, session = adminSession) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const payloads: Record<string, unknown> = {
      "/api/auth/session": session,
      "/api/config": {
        auth_mode: "open",
        is_admin: session.is_admin,
        people_mode: "mock",
        ai_mode: "mock",
        public_search_mode: "mock",
        providers: {},
      },
      "/api/personas": [],
      "/api/contacts": [],
      "/api/drafts": [],
      "/api/admin/overview": {
        accounts: 1,
        administrators: 1,
        saved_contacts: 0,
        drafts: 0,
        documents: 0,
        stored_bytes: 0,
      },
      "/api/admin/users": { items: [], total: 0, offset: 0, limit: 25 },
    };
    await route.fulfill({
      status: path in payloads ? 200 : 500,
      json: payloads[path] ?? { detail: "Unexpected API request" },
    });
  });
}

test("administrator explicitly selects a target email before starting Google linking", async ({
  page,
}) => {
  await mockAdmin(page);
  let starts = 0;
  await page.route("**/api/auth/google/link-admin", async (route) => {
    starts++;
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({
      email: "owner@gmail.com",
    });
    await route.fulfill({
      json: {
        authorization_url:
          "https://accounts.google.com/o/oauth2/v2/auth?state=mock-admin-link",
      },
    });
  });
  await page.route("https://accounts.google.com/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<main>Mock Google account selection</main>",
    }),
  );
  await page.goto("/admin");
  const input = page.getByLabel("Google account email", { exact: true });
  await expect(input).toHaveValue("");
  const button = page.getByRole("button", { name: "Link Google account" });
  await expect(button).toBeDisabled();
  expect(starts).toBe(0);
  await input.fill("Owner@gmail.com");
  await button.click();
  await expect(page).toHaveURL(
    "https://accounts.google.com/o/oauth2/v2/auth?state=mock-admin-link",
  );
  expect(starts).toBe(1);
});

for (const unsafeUrl of [
  "https://accounts.google.com.example.test/oauth",
  "https://credentials@accounts.google.com/oauth",
]) {
  test(`rejects an unsafe authorization destination: ${unsafeUrl}`, async ({
    page,
  }) => {
    await mockAdmin(page);
    await page.route("**/api/auth/google/link-admin", (route) =>
      route.fulfill({ json: { authorization_url: unsafeUrl } }),
    );
    await page.goto("/admin");
    await page.getByLabel("Google account email").fill("owner@gmail.com");
    const button = page.getByRole("button", { name: "Link Google account" });
    await button.click();
    await expect(page.locator(".admin-page").getByRole("alert")).toContainText(
      "invalid Google sign-in URL",
    );
    await expect(page).toHaveURL(/\/admin$/);
    await expect(button).toBeEnabled();
  });
}

test("missing server credentials keep administrator linking unavailable", async ({
  page,
}) => {
  await mockAdmin(page, { ...adminSession, google_configured: false });
  await page.goto("/admin");
  await expect(page.getByRole("status")).toContainText(
    "Google linking is awaiting server configuration",
  );
  await expect(page.getByLabel("Google account email")).toHaveCount(0);
});

test("a success query alone cannot claim a Google account is connected", async ({
  page,
}) => {
  await mockAdmin(page);
  await page.goto("/admin?google_link=success");
  await expect(page.getByLabel("Google account email")).toBeVisible();
  await expect(page.getByText("Google account connected")).toHaveCount(0);
  await expect(page).toHaveURL(/\/admin$/);
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: { ...adminSession, email: "owner@gmail.com", google_linked: true },
    }),
  );
  await page.reload();
  await expect(page.getByRole("status")).toContainText(
    "Google account connected: owner@gmail.com",
  );
  await expect(page.getByLabel("Google account email")).toHaveCount(0);
});

test("a logged-in administrator sees callback failures and can retry", async ({
  page,
}) => {
  await mockAdmin(page);
  await page.goto("/admin?error=google_admin_link_email");
  await expect(page.locator(".admin-page").getByRole("alert")).toContainText(
    "matches the email you entered",
  );
  await expect(page.getByLabel("Google account email")).toBeVisible();
  await expect(page).toHaveURL(/\/admin$/);
});

test("members do not see the administrator migration form", async ({
  page,
}) => {
  await mockAdmin(page, {
    ...adminSession,
    is_admin: false,
    email: "member@gmail.com",
  });
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Administrator access required" }),
  ).toBeVisible();
  await expect(page.getByLabel("Google account email")).toHaveCount(0);
});

test("invalid OAuth state remains visible when an authenticated administrator returns home", async ({
  page,
}) => {
  await mockAdmin(page);
  await page.goto("/?error=google_invalid_state");
  const error = page.locator('.toast[role="alert"]');
  await expect(error).toContainText("expired or belongs to another browser");
  await expect(page).toHaveURL(/\/$/);
  await error.getByRole("button", { name: "Dismiss / 关闭" }).click();
  await expect(error).toHaveCount(0);
});

test("expired administrator linking shows an error on password login with public information links", async ({
  page,
}) => {
  await mockAdmin(page, { ...adminSession, authenticated: false });
  await page.goto("/admin?error=google_admin_link_session");
  await expect(page.locator(".auth-card").getByRole("alert")).toContainText(
    "administrator session has changed or expired",
  );
  await expect(page.getByLabel("Password / 密码")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "About / 关于" }),
  ).toHaveAttribute("href", "/about");
  await expect(
    page.getByRole("link", { name: "Privacy / 隐私政策" }),
  ).toHaveAttribute("href", "/privacy");
  await expect(page).toHaveURL(/\/admin$/);
});
