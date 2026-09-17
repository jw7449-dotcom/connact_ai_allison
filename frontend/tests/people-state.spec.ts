import { test, expect, type Page } from "@playwright/test";
import type { Contact, PeopleJob } from "../lib/types";

async function fixture(page: Page) {
  const contacts: Contact[] = ["Alpha", "Beta"].map((name, i) => ({
    id: String(i + 1),
    name: name + " Person",
    provider: "serpapi",
    provider_id: name,
    saved: true,
    title: "Analyst",
    company: name + " Firm",
    location: "",
    school: "",
    profile_url: "https://www.linkedin.com/in/" + name.toLowerCase(),
    email: "",
    email_status: "not_requested",
    tags: [],
    notes: "",
    domains: {},
    sources: [],
    assessments: [],
    jobs: [],
    professional: {},
  }));
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let holdContact = false,
    holdReads = false,
    finished = false,
    searches = 0,
    contactJobs = 0;
  const history: PeopleJob[] = [];
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.slice(4);
    const reply = (json: unknown, status = 200) =>
      route.fulfill({ json, status });
    if (path === "/auth/session")
      return reply({
        mode: "local",
        authenticated: true,
        workspace_id: "people-test",
        email: null,
      });
    if (path === "/config")
      return reply({
        people_mode: "live",
        ai_mode: "mock",
        public_search_mode: "mock",
        providers: { apify: true },
      });
    if (path === "/personas" || path === "/drafts") return reply([]);
    if (path === "/contacts") return reply(contacts);
    if (path === "/finance/search/jobs") {
      if (req.method() === "GET") return reply(history);
      searches += 1;
      const job: PeopleJob = {
        id: "search-1",
        kind: "search",
        status: "queued",
        error: "",
        retryable: true,
        created_at: "2026-09-08T01:00:00Z",
        input: req.postDataJSON(),
        result: {},
      };
      history.push(job);
      return reply({ job, cached: false }, 202);
    }
    if (path === "/people/jobs/search-1")
      return reply({
        ...history[0],
        status: finished ? "succeeded" : "running",
        result: finished
          ? {
              items: [contacts[0]],
              total: 1,
              page: 1,
              has_more: false,
              total_is_estimate: false,
              phase: "complete",
              profile_progress: {
                total: 1,
                ready: contacts[0].professional?.education?.length ? 1 : 0,
                pending: 0,
                failed:
                  contacts[0].profile_prefetch?.status === "failed" ? 1 : 0,
                skipped: 0,
              },
            }
          : {
              phase: "profiles",
              profile_progress: {
                total: 1,
                ready: 0,
                pending: 1,
                failed: 0,
                skipped: 0,
              },
            },
      });
    const match = path.match(/^\/contacts\/([12])(?:\/(jobs|save))?$/);
    if (match) {
      const c = contacts[Number(match[1]) - 1];
      if (req.method() === "GET") {
        if (holdReads) await held;
        return reply(c);
      }
      if (holdContact && c.id === "1") await held;
      if (match[2] === "jobs") {
        contactJobs += 1;
        return reply(
          { job: { id: "profile-1", status: "queued" }, cached: false },
          202,
        );
      }
      if (match[2] === "save")
        return reply({ contact: c, already_saved: true });
      return reply({ ...c, ...req.postDataJSON() });
    }
    return reply({ detail: "Unexpected fixture path " + path }, 404);
  });
  return {
    hold: () => {
      holdContact = true;
    },
    release,
    holdReads: () => {
      holdReads = true;
    },
    finish: (unavailable = false) => {
      finished = true;
      contacts[0].profile_prefetch = {
        status: unavailable ? "failed" : "succeeded",
        error: unavailable ? "Public profile is unavailable." : "",
      };
      if (!unavailable)
        contacts[0].professional = {
          summary: "Prepared professional biography",
          retrieved_at: "2026-09-09T01:00:00Z",
          experience: [
            {
              title: "Analyst",
              company: "Prepared Firm",
              start_date: "2024",
              end_date: "Present",
              location: "London",
              description: "Professional work details",
            },
          ],
          education: [
            {
              school: "Prepared University",
              degree: "BA",
              field_of_study: "Economics",
              start_date: "2020",
              end_date: "2024",
            },
          ],
        };
    },
    searches: () => searches,
    contactJobs: () => contactJobs,
  };
}

test("closing a contact before a delayed job response cannot reopen or replace another contact", async ({
  page,
}) => {
  const f = await fixture(page);
  f.hold();
  await page.goto("/contacts");
  await page.getByRole("button", { name: /Alpha Person Analyst/ }).click();
  await page.getByRole("button", { name: /Get profile details/ }).click();
  await page.getByRole("button", { name: "Close details" }).click();
  await page.getByRole("button", { name: /Beta Person Analyst/ }).click();
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: "Beta Person" }),
  ).toBeVisible();
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/contacts/1/jobs"),
  );
  f.release();
  await response;
  await page.waitForTimeout(200);
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: "Beta Person" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
});

test("search prepares the page before display and opens details without an enrichment request", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/people");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  await expect(
    page.getByText("Preparing profile details: 0/1. You can leave and return."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Alpha Person Analyst/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Search people", exact: true }),
  ).toBeDisabled();
  f.finish();
  await expect(page.getByText("Profile ready")).toBeVisible();
  f.holdReads();
  await page.getByRole("button", { name: /Alpha Person Analyst/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Prepared professional biography"),
  ).toBeVisible();
  await expect(dialog.getByText("Prepared University")).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: /Get profile details/ }),
  ).toHaveCount(0);
  expect(f.contactJobs()).toBe(0);
  f.release();
});

test("a profile failure preserves the person and explains unavailable details", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/people");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  f.finish(true);
  await expect(page.getByText("Some details unavailable")).toBeVisible();
  await page.getByRole("button", { name: /Alpha Person Analyst/ }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByText(
        /Some public details could not be prepared: Public profile is unavailable/,
      ),
  ).toBeVisible();
  expect(f.contactJobs()).toBe(0);
});

test("search job and parameters restore after leaving the page without another provider request", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/people");
  await page
    .getByLabel("Company / institution", { exact: true })
    .fill("Saved filter");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  await expect(page.getByLabel("Saved searches")).toHaveValue("search-1");
  await page.getByRole("link", { name: "Contacts", exact: true }).click();
  f.finish();
  await page.getByRole("link", { name: "People Search", exact: true }).click();
  await expect(
    page.getByLabel("Company / institution", { exact: true }),
  ).toHaveValue("Saved filter");
  await expect(
    page.getByRole("button", { name: /Alpha Person Analyst/ }),
  ).toBeVisible();
  expect(f.searches()).toBe(1);
});
