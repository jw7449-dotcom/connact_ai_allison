import { test, expect, type Page, type Route } from "@playwright/test";

const sessionUrl = "**/api/auth/session";
// Run against `next build` + `next start`: development StrictMode intentionally
// makes an additional, canceled session read when mounting AuthGate.
const signedOutSession = {
  mode: "invite",
  authenticated: false,
  email: null,
  workspace_id: null,
};

async function startPausedClock(page: Page) {
  const time = new Date("2026-09-09T00:00:00Z");
  await page.clock.install({ time });
  await page.clock.pauseAt(time);
}

async function respondWithSession(route: Route) {
  await route.fulfill({ json: signedOutSession });
}

async function expectReconnecting(page: Page, attempt: number) {
  await expect(page.getByText(/正在重新连接/)).toContainText(`${attempt}/5`);
  await expect(
    page.getByRole("button", { name: "Retry now / 立即重试", exact: true }),
  ).toBeVisible();
}

test.describe("authentication service recovery", () => {
  test.use({ permissions: [] });
  // Every API request is intercepted, so these tests never use a backend or
  // create accounts. Each test supplies its own session/login responses.
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/**", (route) =>
      route.fulfill({
        status: 500,
        json: { detail: "Unexpected API request in isolated recovery test" },
      }),
    );
    await startPausedClock(page);
  });

  for (const failure of [
    {
      name: "an HTML 502 gateway response",
      status: 502,
      contentType: "text/html",
      body: "<html><body>Bad Gateway</body></html>",
    },
    {
      name: "an HTML response with HTTP 200",
      status: 200,
      contentType: "text/html",
      body: "<html><body>Service is starting</body></html>",
    },
    {
      name: "JSON with an invalid session shape",
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "starting" }),
    },
  ]) {
    test(`automatically recovers from ${failure.name}`, async ({ page }) => {
      let requests = 0;
      await page.route(sessionUrl, async (route) => {
        requests += 1;
        if (requests === 1) {
          await route.fulfill({
            status: failure.status,
            contentType: failure.contentType,
            body: failure.body,
          });
        } else {
          await respondWithSession(route);
        }
      });

      await page.goto("/");
      await expectReconnecting(page, 1);
      if (failure.status === 502)
        await page.screenshot({
          path: test.info().outputPath("reconnecting.png"),
        });
      expect(requests).toBe(1);
      await page.clock.runFor(4_999);
      expect(requests).toBe(1);
      await page.clock.runFor(1);
      await expect(
        page.getByRole("heading", { name: "Welcome back" }),
      ).toBeVisible();
      expect(requests).toBe(2);
      await expect(page.getByText(/正在重新连接/)).toHaveCount(0);
      if (failure.status === 502)
        await page.screenshot({
          path: test.info().outputPath("recovered.png"),
        });
    });
  }

  test("automatically recovers from a failed network request", async ({
    page,
  }) => {
    let requests = 0;
    await page.route(sessionUrl, async (route) => {
      requests += 1;
      if (requests === 1) await route.abort("connectionfailed");
      else await respondWithSession(route);
    });

    await page.goto("/");
    await expectReconnecting(page, 1);
    await page.clock.runFor(5_000);
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(requests).toBe(2);
  });

  test("times out a stalled session read before retrying", async ({ page }) => {
    let requests = 0;
    await page.route(sessionUrl, async (route) => {
      requests += 1;
      // Leave the first request pending until AuthGate aborts its fetch.
      if (requests > 1) await respondWithSession(route);
    });

    await page.goto("/");
    await expect.poll(() => requests).toBe(1);
    await page.clock.runFor(14_999);
    await expect(page.getByText(/正在重新连接/)).toHaveCount(0);
    expect(requests).toBe(1);
    await page.clock.runFor(1);
    await expectReconnecting(page, 1);
    expect(requests).toBe(1);
    await page.clock.runFor(5_000);
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(requests).toBe(2);
  });

  test("stops after five retries and allows manual recovery", async ({
    page,
  }) => {
    let requests = 0;
    let recovered = false;
    await page.route(sessionUrl, async (route) => {
      requests += 1;
      if (recovered) await respondWithSession(route);
      else {
        await route.fulfill({
          status: 502,
          contentType: "text/html",
          body: "<html><body>Bad Gateway</body></html>",
        });
      }
    });

    await page.goto("/");
    const delays = [5_000, 10_000, 15_000, 15_000, 15_000];
    for (const [index, delay] of delays.entries()) {
      await expectReconnecting(page, index + 1);
      expect(requests).toBe(index + 1);
      await page.clock.runFor(delay - 1);
      expect(requests).toBe(index + 1);
      await page.clock.runFor(1);
      await expect.poll(() => requests).toBe(index + 2);
    }

    await expect(page.getByText(/服务暂时不可用/)).toBeVisible();
    await expect(page.getByText(/正在重新连接/)).toHaveCount(0);
    const retry = page.getByRole("button", {
      name: "Retry / 重试",
      exact: true,
    });
    await expect(retry).toBeVisible();
    await page.clock.runFor(90_000);
    expect(requests).toBe(6);

    recovered = true;
    await retry.click();
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(requests).toBe(7);
  });

  test("manual retry cancels the pending automatic retry", async ({ page }) => {
    let requests = 0;
    await page.route(sessionUrl, async (route) => {
      requests += 1;
      if (requests === 1) {
        await route.fulfill({
          status: 503,
          contentType: "text/html",
          body: "Service Unavailable",
        });
      } else await respondWithSession(route);
    });

    await page.goto("/");
    await expectReconnecting(page, 1);
    await page.clock.runFor(2_000);
    await page
      .getByRole("button", { name: "Retry now / 立即重试", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(requests).toBe(2);
    await page.clock.runFor(90_000);
    expect(requests).toBe(2);
  });

  test("does not retry a failed login POST and preserves its JSON detail", async ({
    page,
  }) => {
    let sessionRequests = 0;
    let loginRequests = 0;
    const detail = "Sign-in maintenance. Please try again later.";
    await page.route(sessionUrl, async (route) => {
      sessionRequests += 1;
      await respondWithSession(route);
    });
    await page.route("**/api/auth/login", async (route) => {
      loginRequests += 1;
      expect(route.request().method()).toBe("POST");
      await route.fulfill({ status: 503, json: { detail } });
    });

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    await page
      .getByLabel("Email or username / 邮箱或账号")
      .fill("recovery-test@example.invalid");
    await page.getByLabel("Password / 密码").fill("test-password-2026");
    await page
      .getByRole("button", { name: "Sign in / 登录", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toHaveText(detail);
    await expect(
      page.getByRole("button", { name: "Sign in / 登录", exact: true }),
    ).toBeEnabled();
    await page.clock.runFor(90_000);
    expect(loginRequests).toBe(1);
    expect(sessionRequests).toBe(1);
  });

  test("a session 401 stops without recursively requesting the session", async ({
    page,
  }) => {
    let requests = 0;
    const detail = "Please sign in again.";
    await page.route(sessionUrl, async (route) => {
      requests += 1;
      await route.fulfill({ status: 401, json: { detail } });
    });

    await page.goto("/");
    await expect(page.getByText(detail, { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Retry / 重试", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/正在重新连接/)).toHaveCount(0);
    await page.clock.runFor(90_000);
    expect(requests).toBe(1);
  });
});
