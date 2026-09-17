import { test, expect } from "@playwright/test";
import { NextRequest } from "next/server";
import { proxy } from "../proxy";

const canonical = new URL(process.env.E2E_URL || "http://127.0.0.1:3100");
const alias = new URL(canonical);
alias.hostname = canonical.hostname === "localhost" ? "127.0.0.1" : "localhost";

test.describe("Local canonical origin through the real frontend", () => {
  test.skip(
    !["localhost", "127.0.0.1"].includes(canonical.hostname),
    "Requires a local E2E_URL matching the frontend PUBLIC_ORIGIN.",
  );

  test("alias page navigation preserves its path and query on the configured host", async ({
    request,
  }) => {
    const path = "/finance?view=search&next=%2Femail%3Fdraft%3Dtest";
    for (const method of ["GET", "HEAD"]) {
      const response = await request.fetch(new URL(path, alias).href, {
        method,
        maxRedirects: 0,
      });
      expect(response.status()).toBe(307);
      expect(response.headers().location).toBe(new URL(path, canonical).href);
      expect(response.headers()["cache-control"]).toBe("no-store");
    }
  });

  test("the canonical page loads without a redirect loop", async ({
    request,
  }) => {
    const response = await request.get(new URL("/finance", canonical).href, {
      maxRedirects: 0,
    });
    expect(response.status()).toBe(200);
    expect(response.headers().location).toBeUndefined();
    expect(response.headers()["content-type"]).toContain("text/html");
  });

  test("API requests retain their response and reject a hostile origin", async ({
    request,
  }) => {
    const sessionUrl = new URL("/api/auth/session", alias).href;
    const session = await request.get(sessionUrl, { maxRedirects: 0 });
    expect(session.status()).toBe(200);
    expect(session.headers().location).toBeUndefined();
    expect(["local", "invite", "open"]).toContain((await session.json()).mode);

    const rejected = await request.get(sessionUrl, {
      headers: { Origin: "https://evil.example" },
      maxRedirects: 0,
    });
    expect(rejected.status()).toBe(403);
    expect(rejected.headers().location).toBeUndefined();
    expect((await rejected.json()).detail).toContain("origin is not allowed");
  });

  test("public and Next assets remain on the requested host", async ({
    request,
  }) => {
    const icon = await request.get(new URL("/connact-icon.svg", alias).href, {
      maxRedirects: 0,
    });
    expect(icon.status()).toBe(200);
    expect(icon.headers().location).toBeUndefined();
    expect(icon.headers()["content-type"]).toContain("image/svg+xml");

    const page = await request.get(new URL("/finance", canonical).href);
    const scriptPath = /<script[^>]+src="(\/_next\/static\/[^\"]+)"/.exec(
      await page.text(),
    )?.[1];
    expect(scriptPath).toBeDefined();
    const script = await request.get(new URL(scriptPath!, alias).href, {
      maxRedirects: 0,
    });
    expect(script.status()).toBe(200);
    expect(script.headers().location).toBeUndefined();
    expect(script.headers()["content-type"]).toContain("javascript");
  });

  test("Google sign-in starts on the same host as its configured callback", async ({
    request,
  }) => {
    test.skip(
      process.env.E2E_AUTH_PROVIDER !== "google",
      "Requires the Google-provider E2E stack; creates only an OAuth attempt.",
    );
    const start = await request.post(
      new URL("/api/auth/google/start", canonical).href,
      {
        headers: { Origin: canonical.origin },
        data: { next: "/finance", invitation: "" },
        maxRedirects: 0,
      },
    );
    expect(start.status()).toBe(200);
    const authorization = new URL((await start.json()).authorization_url);
    expect(authorization.origin).toBe("https://accounts.google.com");
    expect(authorization.searchParams.get("redirect_uri")).toBe(
      new URL("/api/auth/google/callback", canonical).href,
    );
    const cookies = start
      .headersArray()
      .filter((header) => header.name.toLowerCase() === "set-cookie")
      .map((header) => header.value)
      .join("\n");
    expect(cookies).toMatch(/HttpOnly/i);
    expect(cookies).toMatch(/SameSite=lax/i);
    expect(cookies).not.toMatch(/(?:^|;)\s*Domain=/i);
  });
});

test("canonicalization leaves public hosts, different ports and schemes, and writes unchanged", () => {
  const previousOrigin = process.env.PUBLIC_ORIGIN;
  try {
    for (const scenario of [
      {
        publicOrigin: "https://app.example.test",
        url: "http://localhost:3100/finance",
      },
      {
        publicOrigin: "http://127.0.0.1:3100",
        url: "http://localhost:3190/finance",
      },
      {
        publicOrigin: "http://127.0.0.1:3100",
        url: "https://localhost:3100/finance",
      },
      {
        publicOrigin: "http://127.0.0.1:3100",
        url: "http://evil.example:3100/finance",
      },
      {
        publicOrigin: "http://127.0.0.1:3100",
        url: "http://localhost:3100/finance",
        method: "POST",
      },
    ]) {
      process.env.PUBLIC_ORIGIN = scenario.publicOrigin;
      const response = proxy(
        new NextRequest(scenario.url, {
          method: scenario.method || "GET",
          headers: { Host: new URL(scenario.url).host },
        }),
      );
      expect(response.headers.get("location"), scenario.url).toBeNull();
      expect(response.headers.get("x-middleware-next"), scenario.url).toBe("1");
    }
  } finally {
    if (previousOrigin === undefined) delete process.env.PUBLIC_ORIGIN;
    else process.env.PUBLIC_ORIGIN = previousOrigin;
  }
});
