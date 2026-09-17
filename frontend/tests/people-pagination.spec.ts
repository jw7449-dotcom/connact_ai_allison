import { test, expect, type Page } from "@playwright/test";
import type { Contact, PeopleJob } from "../lib/types";

async function paginationFixture(
  page: Page,
  options: {
    estimated?: boolean;
    missingHasMore?: boolean;
    explicitEnd?: boolean;
    queued?: boolean;
  } = {},
) {
  const contacts: Contact[] = Array.from({ length: 26 }, (_, index) => ({
    id: String(index + 1),
    name: `Person ${String(index + 1).padStart(2, "0")}`,
    provider: "serpapi",
    provider_id: String(index + 1),
    saved: false,
    title: "Analyst",
    company: "Test Firm",
    location: "London",
    school: "",
    profile_url: `https://www.linkedin.com/in/pagination-person-${index + 1}`,
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
  const jobs: PeopleJob[] = [];
  const requests: Record<string, unknown>[] = [];
  let releaseSecond = false;
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.slice(4);
    const reply = (json: unknown, status = 200) =>
      route.fulfill({ json, status });
    if (path === "/auth/session")
      return reply({
        mode: "local",
        authenticated: true,
        workspace_id: "pagination-test",
        email: null,
      });
    if (path === "/config")
      return reply({
        people_mode: "mock",
        ai_mode: "mock",
        public_search_mode: "mock",
        providers: {},
      });
    if (path === "/personas" || path === "/drafts" || path === "/contacts")
      return reply([]);
    if (path === "/finance/search/jobs") {
      if (req.method() === "GET") return reply([...jobs].reverse());
      const input = req.postDataJSON();
      requests.push(input);
      const cached = jobs.find(
        (job) => JSON.stringify(job.input) === JSON.stringify(input),
      );
      if (cached) return reply({ job: cached, cached: true }, 202);
      const current = Number(input.page);
      const job: PeopleJob = {
        id: "pagination-" + (jobs.length + 1),
        kind: "search",
        status: options.queued && current === 2 ? "queued" : "succeeded",
        error: "",
        retryable: true,
        created_at: "2026-09-14T01:00:00Z",
        input,
        result: {
          items: contacts.slice((current - 1) * 10, current * 10),
          total: options.estimated ? 100_000 : 26,
          page: current,
          per_page: 10,
          total_is_estimate: !!options.estimated,
          ...(!options.missingHasMore
            ? { has_more: !options.explicitEnd && current < 3 }
            : {}),
        },
      };
      jobs.push(job);
      return reply({ job, cached: false }, 202);
    }
    if (path.startsWith("/people/jobs/pagination-")) {
      const job = jobs.find((item) => path.endsWith("/" + item.id))!;
      if (job.input.page === 2 && releaseSecond) job.status = "succeeded";
      return reply(job);
    }
    return reply({ detail: "Unexpected test request " + path }, 404);
  });
  return {
    requests,
    finishSecond: () => {
      releaseSecond = true;
    },
  };
}

test("next/previous tens preserve submitted filters and cached pages; a fresh query starts at page one", async ({
  page,
}) => {
  const fixture = await paginationFixture(page);
  await page.goto("/people");
  await page
    .getByLabel("Company / institution", { exact: true })
    .fill("Submitted Firm");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  const pagination = page.getByRole("navigation", {
    name: "Search pagination top",
  });
  await expect(pagination.getByText("1–10 of 26 people")).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(10);
  await expect(
    pagination.getByRole("button", { name: "Previous page" }),
  ).toBeDisabled();

  await page
    .getByLabel("Company / institution", { exact: true })
    .fill("Unsubmitted change");
  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(
    page.getByRole("button", { name: /Person 11 Analyst/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Person 01 Analyst/ }),
  ).toHaveCount(0);
  await expect(pagination.getByText("11–20 of 26 people")).toBeVisible();
  expect(fixture.requests[1]).toMatchObject({
    company: "Submitted Firm",
    page: 2,
    per_page: 10,
  });

  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await expect(
    pagination.getByRole("button", { name: "Next page" }),
  ).toBeDisabled();
  await expect(
    pagination.getByText(/21–26 of 26 people.*End of results/),
  ).toBeVisible();
  await pagination.getByRole("button", { name: "Previous page" }).click();
  await expect(
    page.getByRole("button", { name: /Person 11 Analyst/ }),
  ).toBeVisible();
  await expect(page.getByLabel("Saved searches")).toHaveValue("pagination-2");

  await page
    .getByLabel("Company / institution", { exact: true })
    .fill("New Firm");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  await expect(pagination.getByText("Page 1 of 3")).toBeVisible();
  expect(fixture.requests.at(-1)).toMatchObject({
    company: "New Firm",
    page: 1,
    per_page: 10,
  });
});

test("older full-page results without has_more can continue despite estimated totals", async ({
  page,
}) => {
  await paginationFixture(page, { estimated: true, missingHasMore: true });
  await page.goto("/people");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  const pagination = page.getByRole("navigation", {
    name: "Search pagination top",
  });
  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(
    page.getByRole("button", { name: /Person 11 Analyst/ }),
  ).toBeVisible();
  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(
    page.getByRole("button", { name: /Person 21 Analyst/ }),
  ).toBeVisible();
  await expect(
    pagination.getByRole("button", { name: "Next page" }),
  ).toBeDisabled();
});

test("an explicit last page stops navigation even when Google estimates more results", async ({
  page,
}) => {
  await paginationFixture(page, { estimated: true, explicitEnd: true });
  await page.goto("/people");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Search pagination top" })
      .getByRole("button", { name: "Next page" }),
  ).toBeDisabled();
});

test("pending page preparation disables duplicate navigation and restores the completed second page", async ({
  page,
}) => {
  const fixture = await paginationFixture(page, { queued: true });
  await page.goto("/people");
  await page
    .getByRole("button", { name: "Search people", exact: true })
    .click();
  const pagination = page.getByRole("navigation", {
    name: "Search pagination top",
  });
  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(
    pagination.getByRole("button", { name: "Next page" }),
  ).toBeDisabled();
  await expect(page.getByLabel("Saved searches")).toBeDisabled();
  fixture.finishSecond();
  await expect(pagination.getByText("Page 2 of 3")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Person 11 Analyst/ }),
  ).toBeVisible();
  expect(fixture.requests).toHaveLength(2);
  await page.reload();
  await expect(pagination.getByText("Page 2 of 3")).toBeVisible();
  expect(fixture.requests).toHaveLength(2);
});
