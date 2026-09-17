import { test, expect, type Page } from "@playwright/test";

async function availabilityFixture(
  page: Page,
  availability: () => { status: number; json: unknown },
) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/session")
      return route.fulfill({
        json: {
          mode: "local",
          authenticated: true,
          workspace_id: "mail-availability",
        },
      });
    if (path === "/api/config")
      return route.fulfill({
        json: {
          auth_mode: "local",
          people_mode: "mock",
          ai_mode: "mock",
          public_search_mode: "mock",
          providers: {},
        },
      });
    if (["/api/personas", "/api/contacts", "/api/drafts"].includes(path))
      return route.fulfill({ json: [] });
    if (path === "/api/mailboxes") return route.fulfill(availability());
    return route.fulfill({
      status: 404,
      json: { detail: "Unexpected test endpoint" },
    });
  });
}

test("mailbox API 404 is a service error and can recover without mislabeling OAuth configuration", async ({
  page,
}) => {
  let unavailable = true;
  await availabilityFixture(page, () =>
    unavailable
      ? { status: 404, json: { detail: "Not Found" } }
      : {
          status: 200,
          json: {
            configured: true,
            mailboxes: [],
            callback_uri: "http://127.0.0.1:3100/api/mailboxes/callback",
          },
        },
  );
  await page.goto("/mailboxes");
  await expect(page.locator('.error-panel[role="alert"]')).toContainText(
    "The running backend does not provide the Gmail mailbox API (HTTP 404)",
  );
  await expect(
    page.getByText("Mailbox service unavailable", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Setup required", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", {
      name: "Connect Gmail · send & receive",
      exact: true,
    }),
  ).toBeDisabled();
  await page.getByLabel("Interface language").selectOption("zh");
  await expect(page.locator('.error-panel[role="alert"]')).toContainText(
    "当前运行的后端未提供 Gmail 邮箱接口",
  );
  unavailable = false;
  await page.getByRole("button", { name: "重试邮箱状态", exact: true }).click();
  await expect(page.getByText("OAuth 已配置", { exact: true })).toBeVisible();
  await expect(page.locator('.error-panel[role="alert"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "连接 Gmail · 收发邮件", exact: true }),
  ).toBeEnabled();
});

test("successful unconfigured mailbox response keeps the existing disabled connection gate", async ({
  page,
}) => {
  await availabilityFixture(page, () => ({
    status: 200,
    json: {
      configured: false,
      mailboxes: [],
      callback_uri: "http://127.0.0.1:3100/api/mailboxes/callback",
    },
  }));
  await page.goto("/mailboxes");
  await expect(page.getByText("Setup required", { exact: true })).toBeVisible();
  await expect(page.locator('.error-panel[role="alert"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "Connect Gmail · send & receive",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Connect for sending only", exact: true }),
  ).toBeDisabled();
});
