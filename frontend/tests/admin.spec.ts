import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("open registration, isolated member data, and administrator file inspection", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_AUTH_MODE !== "open",
    "Requires disposable open-registration stack.",
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Create account / 免费注册" }).click();
  await expect(page.getByLabel("Invitation code / 邀请码")).toHaveCount(0);
  await page
    .getByLabel("Email / 邮箱", { exact: true })
    .fill("admin-view-member@example.test");
  await page.getByLabel("Password / 密码").fill("browser-member-test-only");
  await page
    .getByRole("button", { name: "Create account / 注册", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Administration", exact: true }),
  ).toHaveCount(0);
  expect((await page.request.get("/api/admin/users")).status()).toBe(403);
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Administrator access required" }),
  ).toBeVisible();
  const persona = await page.request.post("/api/personas", {
    data: {
      label: "Member background",
      data: { name: "Test Member", education: "Saved university" },
    },
  });
  expect(persona.ok()).toBe(true);
  await page.request.post("/api/drafts", {
    data: {
      subject: "Member's saved draft",
      body_html: "<p>Saved draft body</p>",
    },
  });
  const original = readFileSync("../demo/sample-resume.docx");
  const upload = await page.request.post("/api/documents/jobs", {
    multipart: {
      file: {
        name: "member-resume.docx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: original,
      },
    },
  });
  expect(upload.status()).toBe(202);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email or username / 邮箱或账号").fill("admin");
  await page.getByLabel("Password / 密码").fill("browser-admin-test-only");
  await page
    .getByRole("button", { name: "Sign in / 登录", exact: true })
    .click();
  await page.getByRole("link", { name: "Administration", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Administration", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search accounts").fill("admin-view-member");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page
    .getByRole("button", {
      name: "View account admin-view-member@example.test",
      exact: true,
    })
    .click();
  await page
    .locator(".admin-record summary")
    .filter({ hasText: "Member background" })
    .click();
  await expect(
    page.locator(".admin-value").filter({ hasText: "Saved university" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Email drafts 1", exact: true })
    .click();
  await page
    .locator(".admin-record summary")
    .filter({ hasText: "Member's saved draft" })
    .click();
  await expect(
    page.locator(".admin-value").filter({ hasText: "Saved draft body" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Files 1", exact: true }).click();
  await page
    .locator(".admin-record summary")
    .filter({ hasText: "member-resume.docx" })
    .click();
  const link = page.getByRole("link", {
    name: "Download original",
    exact: true,
  });
  const response = await page.request.get((await link.getAttribute("href"))!);
  expect(response.status()).toBe(200);
  expect(await response.body()).toEqual(original);
  await page.screenshot({
    path: "test-results/admin-files.png",
    fullPage: true,
  });
});
