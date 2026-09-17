import { test, expect } from "@playwright/test";

// Run only against tests/mail-api-server.py through Next's real API proxy.
test.describe("Gmail real route browser integration", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(
    process.env.MAIL_E2E !== "1",
    "Requires the isolated mail API test server.",
  );

  test.afterAll(async ({ request }) => {
    // Health check also confirms no browser flow replaced the real proxy routes.
    expect((await request.get("/api/health")).ok()).toBeTruthy();
  });

  test("missing OAuth configuration, mailbox PATCH settings and private inbox operations", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    const trackers: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (req) => {
      if (req.url().includes("tracker.invalid")) trackers.push(req.url());
    });
    await page.goto("/mailboxes");
    await expect(
      page.getByRole("button", { name: "Connect Gmail · send & receive" }),
    ).toBeDisabled();
    await expect(
      page.getByText("Setup required", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "sender@example.test", exact: true })
      .click();
    await page
      .getByLabel("Email signature", { exact: true })
      .fill("Updated test signature");
    await page.getByLabel("Timezone · IANA name").fill("Asia/Shanghai");
    await page
      .getByRole("button", { name: "Save sender settings", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const boxes = await (await request.get("/api/mailboxes")).json();
    expect(boxes.mailboxes[0].signature_html).toContain(
      "Updated test signature",
    );
    expect(boxes.mailboxes[0].timezone).toBe("Asia/Shanghai");
    await page.goto("/inbox");
    await expect(
      page.getByRole("button", { name: /Saved Contact/ }),
    ).toBeVisible();
    await expect(page.getByText("PRIVATE UNSAVED MESSAGE")).toHaveCount(0);
    await page.getByRole("button", { name: /Saved Contact/ }).click();
    await expect(
      page.getByRole("region", { name: "Email conversation" }),
    ).toContainText("A reply from the saved contact.");
    await expect(page.getByText("PRIVATE UNSAVED MESSAGE")).toHaveCount(0);
    await page.getByRole("button", { name: "Mark read", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Mark unread", exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Private workspace notes")
      .fill("Private workflow note");
    await page.getByLabel("Contact intent").selectOption("interested");
    await page.getByRole("button", { name: "Save notes", exact: true }).click();
    await expect(page.getByText("Conversation notes saved.")).toBeVisible();
    const thread = await (
      await request.get(
        "/api/mail/threads/shared-thread?mailbox_id=test-mailbox",
      )
    ).json();
    expect(thread.notes).toBe("Private workflow note");
    expect(thread.messages).toHaveLength(1);
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: /contact.txt/ }).click();
    expect((await download).suggestedFilename()).toBe("contact.txt");
    expect(trackers).toEqual([]);
    expect(errors).toEqual([]);
  });

  test("draft review gates send, attachment reaches Gmail transport once, schedule pause resume cancel", async ({
    page,
    request,
  }) => {
    await page.goto("/email?draft=test-draft");
    await expect(page.getByLabel("Sender · Gmail mailbox")).toHaveValue(
      "test-mailbox",
    );
    await page
      .getByLabel("Attachments · up to 5 files / 8 MB total")
      .setInputFiles({
        name: "review.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Reviewed attachment"),
      });
    await page
      .getByRole("button", { name: "Review & send", exact: true })
      .click();
    const review = page.getByRole("dialog", { name: "Confirm Gmail delivery" });
    await expect(review).toContainText("Updated test signature");
    await expect(review).toContainText("contact@example.test");
    await expect(review).toContainText("review.txt");
    await expect(
      review.getByRole("button", { name: "Confirm send", exact: true }),
    ).toBeDisabled();
    expect(
      await (await request.get("/api/test-mail/deliveries")).json(),
    ).toHaveLength(0);
    await review
      .getByRole("button", { name: "Mark this content reviewed" })
      .click();
    await expect(
      review.getByRole("button", { name: "Confirm send", exact: true }),
    ).toBeEnabled();
    await review
      .getByRole("button", { name: "Confirm send", exact: true })
      .click();
    await expect(review).toHaveCount(0);
    const deliveries = await (
      await request.get("/api/test-mail/deliveries")
    ).json();
    expect(deliveries).toHaveLength(1);
    expect(deliveries[0]).toMatchObject({
      to: "contact@example.test",
      attachments: ["review.txt"],
    });
    await page.getByLabel("Delivery", { exact: true }).selectOption("schedule");
    const future = new Date(Date.now() + 3600_000);
    future.setMinutes(future.getMinutes() - future.getTimezoneOffset());
    await page
      .getByLabel("Send at · your local time")
      .fill(future.toISOString().slice(0, 16));
    await page
      .getByRole("button", { name: "Review & send", exact: true })
      .click();
    await review
      .getByRole("button", { name: "Confirm schedule", exact: true })
      .click();
    await expect(review).toHaveCount(0);
    await page.goto("/outbox");
    await page.getByRole("button", { name: "Pause", exact: true }).click();
    await page
      .getByRole("button", { name: "Review & resume", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText(
      "Updated test signature",
    );
    await page
      .getByRole("button", { name: "Confirm resume", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Cancel delivery", exact: true })
      .click();
    await expect(page.getByText("cancelled", { exact: true })).toBeVisible();
    expect(
      await (await request.get("/api/test-mail/deliveries")).json(),
    ).toHaveLength(1);
  });

  test("original-thread reply keeps recipient, manual follow-up and suppression use actual PATCH API", async ({
    page,
    request,
  }) => {
    await page.goto("/inbox");
    await page.getByRole("button", { name: /Saved Contact/ }).click();
    await page
      .getByRole("button", { name: "Reply in Gmail thread", exact: true })
      .click();
    await expect(page.getByLabel("To · Contact")).toBeDisabled();
    await page
      .getByRole("textbox", { name: "Email body", exact: true })
      .fill("Thank you for your reply.");
    await page
      .getByRole("button", { name: "Review & send", exact: true })
      .click();
    const review = page.getByRole("dialog", { name: "Confirm Gmail delivery" });
    await expect(review).toContainText("Re: Original conversation");
    await review
      .getByRole("button", { name: "Mark this content reviewed", exact: true })
      .click();
    await review
      .getByRole("button", { name: "Confirm send", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const deliveries = await (
      await request.get("/api/test-mail/deliveries")
    ).json();
    expect(deliveries.at(-1)).toMatchObject({
      to: "contact@example.test",
      thread_id: "shared-thread",
      in_reply_to: "<visible-message@example.test>",
    });
    await page
      .getByRole("button", { name: /Saved Contact/ })
      .first()
      .click();
    await page
      .getByRole("button", { name: "Add follow-up", exact: true })
      .click();
    await page.getByLabel("Task", { exact: true }).fill("Check reply manually");
    await page.getByLabel("Due · your local time").fill("2027-01-01T10:00");
    await page
      .getByRole("button", { name: "Create follow-up", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.goto("/followups");
    await expect(page.getByText("Check reply manually")).toBeVisible();
    await page.getByRole("button", { name: "Complete", exact: true }).click();
    await expect(page.getByText("completed", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Add suppression", exact: true })
      .click();
    await page
      .getByLabel("Contact", { exact: true })
      .selectOption("test-contact");
    await page
      .getByLabel("Reason", { exact: true })
      .selectOption("unsubscribe");
    await page
      .getByRole("button", { name: "Confirm stop contacting", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(
      await (await request.get("/api/mail/suppressions")).json(),
    ).toMatchObject([{ email: "contact@example.test", reason: "unsubscribe" }]);
  });

  test("exact email and domain, intent and pending-reply filters reset paginated contact mail", async ({
    page,
    request,
  }) => {
    expect(
      (await request.post("/api/test-mail/seed-pagination")).ok(),
    ).toBeTruthy();
    await page.goto("/inbox?mailbox=pagination-mailbox");
    const tiles = page.locator(".mail-message-tile");
    await expect(tiles).toHaveCount(200);
    const nextPage = page.waitForRequest(
      (req) =>
        req.url().includes("/api/mail/messages?") &&
        new URL(req.url()).searchParams.get("offset") === "200",
    );
    await page
      .getByRole("button", { name: "Load more messages", exact: true })
      .click();
    await nextPage;
    await expect(tiles).toHaveCount(204);
    expect(new Set(await tiles.allTextContents()).size).toBe(204);
    await expect(
      page.getByRole("button", { name: "Load more messages" }),
    ).toHaveCount(0);
    await page
      .getByLabel("Contact email · exact")
      .fill("PAGES@PAGES.EXAMPLE.TEST");
    await page
      .getByRole("button", { name: "Apply filters", exact: true })
      .click();
    await expect(tiles).toHaveCount(200);
    await expect(
      page.getByRole("button", { name: /Other Contact/ }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Load more messages", exact: true })
      .click();
    await expect(tiles).toHaveCount(202);
    await page.getByLabel("Contact email · exact").fill("");
    await page.getByLabel("Email domain · exact").fill("pages.example.test");
    await page
      .getByRole("button", { name: "Apply filters", exact: true })
      .click();
    await expect(tiles).toHaveCount(200);
    await expect(
      page.getByRole("button", { name: /Subdomain Contact/ }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Load more messages", exact: true })
      .click();
    await expect(tiles).toHaveCount(202);
    await page
      .getByRole("button", { name: "Clear filters", exact: true })
      .click();
    await page
      .getByLabel("Contact email · exact")
      .fill("other@other.example.test");
    await page
      .getByRole("button", { name: "Apply filters", exact: true })
      .click();
    await expect(tiles).toHaveCount(1);
    await page.getByLabel("Awaiting my reply").check();
    await expect(tiles).toHaveCount(0);
    await expect(
      page.getByText("No contact emails here", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Awaiting my reply").uncheck();
    await expect(tiles).toHaveCount(1);
    await page
      .getByRole("button", { name: "Clear filters", exact: true })
      .click();
    await page.getByLabel("Intent filter").selectOption("interested");
    await expect(tiles).toHaveCount(200);
    await expect(
      page.getByRole("button", { name: /Other Contact/ }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: /Pagination Contact/ })
      .first()
      .click();
    await expect(
      page.getByRole("link", { name: "Review follow-ups", exact: true }),
    ).toBeVisible();
    await page.getByLabel("Intent filter").selectOption("none");
    await expect(tiles).toHaveCount(2);
    await expect(
      page.getByRole("button", { name: /Pagination Contact/ }),
    ).toHaveCount(0);
  });
});
