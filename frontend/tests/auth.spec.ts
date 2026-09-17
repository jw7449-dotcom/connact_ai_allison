import { test, expect } from "@playwright/test";

test("invitation, login, logout, and browser sessions keep workspaces isolated", async ({
  page,
  browser,
  request,
  baseURL,
}) => {
  test.skip(
    process.env.E2E_AUTH_MODE !== "invite",
    "Run with the disposable invitation-mode E2E stack.",
  );
  const email = process.env.E2E_TEST_EMAIL!,
    invitation = process.env.E2E_INVITATION!;
  const password = "browser-test-password-2026";
  expect((await request.get("/api/drafts")).status()).toBe(401);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Have an invitation? Create account / 邀请注册",
    })
    .click();
  await page.getByLabel("Email / 邮箱").fill(email);
  await page.getByLabel("Password / 密码").fill(password);
  await page.getByLabel("Invitation code / 邀请码").fill(invitation);
  await page
    .getByRole("button", { name: "Create account / 注册", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  const cookie = (await page.context().cookies()).find(
    (item) => item.name === "connact_session",
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  await page.goto("/email");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Only the invited owner can read this draft");
  await expect(
    page.getByText("All changes saved", { exact: true }),
  ).toBeVisible();
  const draftId = new URL(page.url()).searchParams.get("draft")!;
  expect((await page.request.get("/api/drafts/" + draftId)).status()).toBe(200);

  const other = await browser.newContext({ baseURL });
  try {
    const joined = await other.request.post("/api/auth/join", {
      data: {
        email: process.env.E2E_SECOND_EMAIL,
        invitation: process.env.E2E_SECOND_INVITATION,
        password,
      },
    });
    expect(joined.ok()).toBe(true);
    expect((await other.request.get("/api/drafts/" + draftId)).status()).toBe(
      404,
    );
    expect(await (await other.request.get("/api/drafts")).json()).toEqual([]);
  } finally {
    await other.close();
  }

  await page
    .getByLabel("Subject", { exact: true })
    .fill("The last edit is flushed before sign out");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  expect((await page.request.get("/api/drafts/" + draftId)).status()).toBe(401);
  await page.getByLabel("Email or username / 邮箱或账号").fill(email);
  await page.getByLabel("Password / 密码").fill("incorrect-test-password");
  await page
    .getByRole("button", { name: "Sign in / 登录", exact: true })
    .click();
  await expect(page.locator(".auth-card [role=alert]")).toContainText(
    "Email or password is incorrect",
  );
  await page.getByLabel("Password / 密码").fill(password);
  await page
    .getByRole("button", { name: "Sign in / 登录", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await page.goto("/email?draft=" + draftId);
  await expect(page.getByLabel("Subject", { exact: true })).toHaveValue(
    "The last edit is flushed before sign out",
  );
});
