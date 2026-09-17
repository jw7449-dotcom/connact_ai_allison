import { test, expect } from "@playwright/test";

const googleSession = {
  mode: "open",
  authenticated: false,
  provider: "google",
  google_configured: true,
  email: null,
  workspace_id: null,
};

test.describe("Google login screen", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/**", (route) =>
      route.fulfill({
        status: 500,
        json: { detail: "Unexpected API request" },
      }),
    );
    await page.route("**/api/auth/session", (route) =>
      route.fulfill({ json: googleSession }),
    );
  });

  test("starts Google sign-in with the current destination and no password form", async ({
    page,
  }) => {
    let starts = 0;
    await page.route("**/api/auth/google/start", async (route) => {
      starts++;
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({
        next: "/finance?view=search",
        invitation: "",
      });
      await route.fulfill({
        json: {
          authorization_url:
            "https://accounts.google.com/o/oauth2/v2/auth?state=isolated",
        },
      });
    });
    await page.route("https://accounts.google.com/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<main>Isolated Google authorization screen</main>",
      }),
    );
    await page.goto("/finance?view=search");
    await expect(
      page.getByRole("heading", { name: "Welcome to Connact.ai" }),
    ).toBeVisible();
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath("google-login.png") });
    await page
      .getByRole("button", { name: "Continue with Google / 使用 Google 登录" })
      .click();
    await expect(page).toHaveURL(
      /https:\/\/accounts.google.com\/o\/oauth2\/v2\/auth/,
    );
    expect(starts).toBe(1);
  });

  test("shows missing server configuration without falling back to a password", async ({
    page,
  }) => {
    await page.route("**/api/auth/session", (route) =>
      route.fulfill({ json: { ...googleSession, google_configured: false } }),
    );
    await page.goto("/");
    await expect(
      page.getByRole("button", {
        name: "Continue with Google / 使用 Google 登录",
      }),
    ).toBeDisabled();
    await expect(page.getByRole("status")).toContainText(
      "awaiting server configuration",
    );
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
  });

  test("displays callback errors and removes them from the URL", async ({
    page,
  }) => {
    await page.goto("/?error=google_invalid_state");
    await expect(page.locator(".auth-card").getByRole("alert")).toContainText("登录请求已失效");
    await expect(page).toHaveURL(/\/$/);
  });

  test("submits an invitation in the POST body and lets a failed start be retried", async ({
    page,
  }) => {
    await page.route("**/api/auth/session", (route) =>
      route.fulfill({ json: { ...googleSession, mode: "invite" } }),
    );
    let starts = 0;
    await page.route("**/api/auth/google/start", async (route) => {
      starts++;
      expect(route.request().postDataJSON().invitation).toBe(
        "isolated-invitation",
      );
      expect(route.request().url()).not.toContain("isolated-invitation");
      await route.fulfill({
        status: 503,
        json: { detail: "Google is temporarily unavailable." },
      });
    });
    await page.goto("/");
    await page
      .getByLabel("Invitation code for new accounts / 新账号邀请码")
      .fill("isolated-invitation");
    const button = page.getByRole("button", {
      name: "Continue with Google / 使用 Google 登录",
    });
    await button.click();
    await expect(page.locator(".auth-card").getByRole("alert")).toHaveText(
      "Google is temporarily unavailable.",
    );
    await expect(button).toBeEnabled();
    expect(starts).toBe(1);
  });
});

test("real same-origin proxy forwards Google redirects and OAuth cookies to the browser", async ({
  request,
}) => {
  test.skip(
    process.env.E2E_AUTH_PROVIDER !== "google",
    "Use the isolated Google-provider E2E stack.",
  );
  const start = await request.get("/api/auth/google/start?next=/finance", {
    maxRedirects: 0,
  });
  expect([302, 303, 307]).toContain(start.status());
  const target = new URL(start.headers().location);
  expect(target.origin).toBe("https://accounts.google.com");
  expect(target.searchParams.get("redirect_uri")).toBe(
    process.env.E2E_URL + "/api/auth/google/callback",
  );
  expect(target.searchParams.get("scope")).toContain("openid");
  expect(target.searchParams.get("scope")).not.toContain("gmail");
  const cookies = start
    .headersArray()
    .filter((h) => h.name.toLowerCase() === "set-cookie")
    .map((h) => h.value)
    .join("\n");
  expect(cookies).toMatch(/HttpOnly/i);
  expect(cookies).toMatch(/SameSite=lax/i);
  const callback = await request.get(
    "/api/auth/google/callback?state=wrong&code=never-exchanged",
    { maxRedirects: 0 },
  );
  expect([302, 303, 307]).toContain(callback.status());
  expect(callback.headers().location).toContain("error=google_");
  expect(
    callback
      .headersArray()
      .some(
        (h) =>
          h.name.toLowerCase() === "set-cookie" && /Max-Age=0/i.test(h.value),
      ),
  ).toBe(true);
  expect(
    (await (await request.get("/api/auth/session")).json()).authenticated,
  ).toBe(false);
});
