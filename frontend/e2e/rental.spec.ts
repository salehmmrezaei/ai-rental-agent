import { test, expect } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import AxeBuilder from "@axe-core/playwright";
async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/(admin|tenant|landlord)$/);
  await expect(
    page.getByRole("heading", { name: /Welcome back/ }),
  ).toBeVisible();
}
function dateIn(days: number) {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}
async function findAcrossPages(page: Page, record: Locator) {
  while (true) {
    await expect(page.locator(".record-card").first()).toBeVisible();
    await expect(page.locator(".loading")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Listing review", exact: true }),
    ).toHaveCount(0);
    if (await record.isVisible()) return;
    const pagination = page.getByRole("navigation", {
      name: "Pagination",
      exact: true,
    });
    const next = pagination.getByRole("button", { name: "Next", exact: true });
    if (!(await next.isVisible()) || !(await next.isEnabled())) {
      await expect(record).toBeVisible();
      return;
    }
    const position = pagination.locator("span");
    const previous = await position.innerText();
    await next.click();
    await expect(position).not.toHaveText(previous);
  }
}
test("real landlord, agency and tenant workflows persist through reloads", async ({
  browser,
}) => {
  const suffix = randomUUID().slice(0, 8);
  const password = randomUUID() + randomUUID();
  const title = `Synthetic Browser Home ${suffix}`;
  const ownerContext = await browser.newContext();
  const agentContext = await browser.newContext();
  const tenantContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  const agent = await agentContext.newPage();
  const tenant = await tenantContext.newPage();
  const errors: string[] = [];
  for (const page of [owner, agent, tenant])
    page.on("pageerror", (error) => errors.push(error.message));
  await owner.goto("/register?role=landlord");
  await owner.getByLabel("Full name").fill("Synthetic Browser Owner");
  await owner
    .getByLabel("Email address")
    .fill(`synthetic.browser.owner.${suffix}@example.com`);
  await owner.getByLabel("Password", { exact: true }).fill(password);
  await owner.getByRole("button", { name: "Create account" }).click();
  await expect(owner).toHaveURL(/\/landlord$/);
  await owner.getByRole("link", { name: "My properties", exact: true }).click();
  await owner.getByRole("link", { name: "Add property", exact: true }).click();
  for (const [label, value] of [
    ["Property title", title],
    ["Description", "Synthetic property for browser verification."],
    ["City", "Bologna"],
    ["Postal code", "40121"],
    ["Address", "Synthetic Via Esempio 42"],
    ["Amenities", "WiFi, balcony"],
  ])
    await owner.getByLabel(label, { exact: true }).fill(value);
  await owner.getByRole("button", { name: "Create property" }).click();
  await expect(
    owner.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await owner.getByRole("button", { name: "Add rental unit" }).click();
  await owner.getByLabel("Rental type").selectOption("room");
  await owner.getByLabel("Unit name").fill("Synthetic Room A");
  await owner.getByLabel("Monthly rent (€)").fill("650");
  await owner.getByRole("button", { name: "Save changes" }).click();
  await expect(
    owner.getByRole("heading", { name: "Synthetic Room A", exact: true }),
  ).toBeVisible();
  await owner.getByRole("button", { name: "Edit unit", exact: true }).click();
  await owner.getByLabel("Monthly rent (€)").fill("675");
  await owner.getByRole("button", { name: "Save changes" }).click();
  await expect(owner.getByText("€675.00", { exact: true })).toBeVisible();
  await owner.getByRole("button", { name: "Pictures", exact: false }).click();
  await owner
    .getByRole("button", { name: "Upload photo", exact: true })
    .click();
  await owner.getByLabel("Photo file").setInputFiles({
    name: "synthetic-photo.png",
    mimeType: "image/png",
    buffer: Buffer.from(process.env.E2E_IMAGE_PNG!, "base64"),
  });
  await owner
    .getByLabel("Photo description")
    .fill("Synthetic property photograph");
  await owner
    .getByRole("button", { name: "Upload photo", exact: true })
    .last()
    .click();
  await expect(
    owner.getByRole("img", { name: "Synthetic property photograph" }),
  ).toBeVisible();
  await owner
    .getByRole("button", { name: "Rooms & listings", exact: false })
    .click();
  await owner
    .getByRole("button", { name: "Create listing", exact: true })
    .click();
  await owner.getByLabel("Available from").fill(dateIn(0));
  await owner.getByLabel("Available until (optional)").fill(dateIn(365));
  await owner.getByRole("button", { name: "Save changes" }).click();
  await owner.getByRole("button", { name: "Submit for review" }).click();
  await expect(owner.getByText("submitted", { exact: true })).toBeVisible();
  await expect(
    owner.getByRole("button", { name: "Edit unit", exact: true }),
  ).toBeDisabled();
  await signIn(
    agent,
    process.env.E2E_ADMIN_EMAIL!,
    process.env.E2E_ADMIN_PASSWORD!,
  );
  await agent
    .getByRole("link", { name: "Listing approvals", exact: true })
    .click();
  const review = agent
    .locator(".record-card")
    .filter({ has: agent.getByRole("heading", { name: title, exact: true }) });
  await findAcrossPages(agent, review);
  await review.getByRole("button", { name: "Approve listing" }).click();
  await agent.getByRole("button", { name: "Confirm approval" }).click();
  await expect(agent.getByRole("dialog")).toHaveCount(0);
  await agent.getByLabel("Listing status").selectOption("approved");
  const approved = agent
    .locator(".record-card")
    .filter({ has: agent.getByRole("heading", { name: title, exact: true }) });
  await findAcrossPages(agent, approved);
  await approved.getByRole("button", { name: "Publish listing" }).click();
  await agent.getByRole("button", { name: "Confirm publication" }).click();
  await expect(agent.getByRole("dialog")).toHaveCount(0);
  await tenant.goto("/listings?city=Bologna&property_type=room");
  await tenant.getByRole("link", { name: title, exact: true }).click();
  await expect(
    tenant.getByRole("img", { name: "Synthetic property photograph" }),
  ).toBeVisible();
  await tenant.getByRole("button", { name: "Save home", exact: true }).click();
  await expect(tenant).toHaveURL(/\/login/);
  await tenant
    .getByRole("link", { name: "Create an account", exact: true })
    .click();
  await tenant.getByLabel("Full name").fill("Synthetic Browser Tenant");
  await tenant
    .getByLabel("Email address")
    .fill(`synthetic.browser.tenant.${suffix}@example.com`);
  await tenant.getByLabel("Password", { exact: true }).fill(password);
  await tenant.getByRole("button", { name: "Create account" }).click();
  await expect(
    tenant.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await tenant.getByRole("button", { name: "Save home", exact: true }).click();
  await expect(
    tenant.getByRole("button", { name: "Saved", exact: true }),
  ).toBeDisabled();
  await tenant.getByLabel("Move-in").fill(dateIn(10));
  await tenant.getByLabel("Move-out").fill(dateIn(60));
  await tenant.getByRole("button", { name: "Check dates" }).click();
  await expect(tenant.getByText("Available for these dates.")).toBeVisible();
  await tenant.getByRole("button", { name: "Apply for this home" }).click();
  await tenant.getByRole("button", { name: "Submit application" }).click();
  await expect(tenant).toHaveURL(/\/tenant\/applications/);
  await expect(
    tenant.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await tenant.reload();
  await expect(
    tenant.locator(".badge").filter({ hasText: /^submitted$/ }),
  ).toBeVisible();
  await agent.getByRole("link", { name: "Applications", exact: true }).click();
  const request = agent
    .locator(".record-card")
    .filter({ has: agent.getByRole("heading", { name: title, exact: true }) });
  await request
    .getByRole("button", { name: "Approve & create contract" })
    .click();
  await agent.getByRole("button", { name: "Confirm approval" }).click();
  await expect(agent.getByRole("dialog")).toHaveCount(0);
  await tenant.getByRole("link", { name: "My rentals", exact: true }).click();
  await expect(
    tenant.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(
    tenant.locator(".badge").filter({ hasText: /^confirmed$/ }),
  ).toBeVisible();
  await owner
    .getByRole("link", { name: "Rental history", exact: true })
    .click();
  await expect(
    owner.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(
    owner.getByText("Tenant information is kept private by the agency."),
  ).toBeVisible();
  await owner.getByRole("link", { name: "Occupancy", exact: true }).click();
  await expect(owner.getByText(title, { exact: true })).toBeVisible();
  await tenant.goto("/listings?city=Bologna");
  await tenant.getByRole("link", { name: title, exact: true }).click();
  await tenant.getByRole("button", { name: "Request a visit" }).click();
  await tenant
    .getByLabel("Preferred time (your local time)")
    .fill(`${dateIn(3)}T10:00`);
  await tenant.getByRole("button", { name: "Send visit request" }).click();
  await expect(
    tenant.locator(".badge").filter({ hasText: /^requested$/ }),
  ).toBeVisible();
  await agent
    .getByRole("link", { name: "Visit scheduling", exact: true })
    .click();
  await agent
    .getByLabel("Visit status", { exact: true })
    .selectOption("requested");
  const visit = agent
    .locator(".record-card")
    .filter({ has: agent.getByRole("heading", { name: title, exact: true }) });
  await findAcrossPages(agent, visit);
  await visit.getByRole("button", { name: "Schedule visit" }).click();
  await agent
    .getByLabel("Visit time (your local time)")
    .fill(`${dateIn(4)}T11:00`);
  await agent.getByRole("button", { name: "Confirm schedule" }).click();
  await expect(agent.getByRole("dialog")).toHaveCount(0);
  await tenant.reload();
  await expect(
    tenant.locator(".badge").filter({ hasText: /^scheduled$/ }),
  ).toBeVisible();
  await tenant
    .getByRole("link", { name: "Agency messages", exact: true })
    .click();
  await tenant.getByRole("button", { name: "New conversation" }).click();
  await tenant.getByLabel("Subject").fill(`Synthetic question ${suffix}`);
  await tenant
    .getByLabel("Your message")
    .fill("Could you confirm the visit arrangements?");
  await tenant
    .getByRole("button", { name: "Send message", exact: true })
    .click();
  await expect(
    tenant.getByText("Could you confirm the visit arrangements?"),
  ).toBeVisible();
  await agent
    .getByRole("link", { name: "Messaging inbox", exact: true })
    .click();
  await agent
    .getByRole("button", { name: new RegExp(`Synthetic question ${suffix}`) })
    .click();
  await agent.getByLabel("Your reply").fill("Your visit is confirmed.");
  await agent.getByRole("button", { name: "Send reply" }).click();
  await expect(agent.getByText("Your visit is confirmed.")).toBeVisible();
  await tenant.reload();
  await expect(tenant.getByText("Your visit is confirmed.")).toBeVisible();
  await tenant.getByRole("button", { name: "Mark 1 as read" }).click();
  await expect(
    tenant.getByRole("button", { name: "Mark 1 as read" }),
  ).toHaveCount(0);
  await tenant.goto("/admin/users");
  await expect(tenant).toHaveURL(/\/tenant$/);
  await tenant.getByRole("link", { name: "Saved homes", exact: true }).click();
  await expect(
    tenant.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await tenant.getByRole("button", { name: "Remove saved home" }).click();
  await expect(tenant.getByText("A little room for inspiration")).toBeVisible();
  expect(errors).toEqual([]);
  await ownerContext.close();
  await agentContext.close();
  await tenantContext.close();
});

test("seeded demo accounts show persisted rental data and searchable homes", async ({
  page,
}) => {
  test.skip(!process.env.E2E_DEMO_PASSWORD, "Requires the phase 6 demo seed");
  const password = process.env.E2E_DEMO_PASSWORD!;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const role of ["tenant", "landlord", "admin"] as const) {
    await page.context().clearCookies();
    await page.goto("/");
    await page.evaluate(() => localStorage.clear());
    await signIn(
      page,
      `demo.${role === "admin" ? "agency" : role}@example.com`,
      password,
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: /Welcome back/ }),
    ).toBeVisible();
    const routes =
      role === "tenant"
        ? ["applications", "contracts", "visits", "messages", "saved"]
        : role === "landlord"
          ? ["properties", "contracts", "occupancy"]
          : [
              "properties",
              "listings",
              "applications",
              "contracts",
              "visits",
              "messages",
              "occupancy",
              "users",
            ];
    for (const route of routes) {
      await page.goto(`/${role}/${route}`);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator(".loading")).toHaveCount(0);
      await expect(page.locator(".notice-error")).toHaveCount(0);
      if (route === "messages")
        await expect(page.locator(".conversation-item").first()).toBeVisible();
      else await expect(page.locator(".empty")).toHaveCount(0);
    }
    if (role === "landlord") {
      await page.goto("/landlord/properties");
      await expect(
        page.getByRole("heading", {
          name: "Demo Bologna home 001",
          exact: true,
        }),
      ).toBeVisible();
    }
    if (role === "tenant") {
      await page.goto("/tenant/contracts");
      await expect(
        page.locator(".badge").filter({ hasText: /^active$/ }),
      ).toBeVisible();
      await page.goto("/tenant/messages");
      await page
        .getByRole("button", { name: /Demo viewing arrangements 001/ })
        .click();
      await expect(
        page.getByText("The agency can help. Which day suits you?"),
      ).toBeVisible();
    }
  }
  await page.goto("/listings?city=Milan&property_type=room&sort=price_asc");
  await expect(page.locator(".loading")).toHaveCount(0);
  await expect(page.locator(".notice-error")).toHaveCount(0);
  const cards = page.locator(".listing-card");
  await expect(cards.first()).toBeVisible();
  await expect(cards).toHaveCount(12);
  await expect(cards.first()).toContainText("Milan");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(cards.first()).toBeVisible();
  expect(errors).toEqual([]);
});
test("public desktop and mobile pages are accessible and do not overflow", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Your next chapter/ }),
    ).toBeVisible();
    await expect(page.locator(".loading")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.screenshot({
      path: `/private/tmp/casa-home-${width}.png`,
      fullPage: true,
    });
    if (width === 390) {
      await page.getByRole("button", { name: "Toggle navigation" }).click();
      await page
        .getByRole("link", { name: "Find a home", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Find your next home" }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    }
  }
});

test("agency dashboards are accessible on desktop and mobile", async ({
  page,
}) => {
  await signIn(
    page,
    process.env.E2E_ADMIN_EMAIL!,
    process.env.E2E_ADMIN_PASSWORD!,
  );
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of [
      "/admin",
      "/admin/users",
      "/admin/properties",
      "/admin/listings",
      "/admin/applications",
      "/admin/contracts",
      "/admin/visits",
      "/admin/messages",
      "/admin/occupancy",
      "/admin/profile",
    ]) {
      await page.goto(route);
      await expect(page).toHaveURL(new RegExp(route + "$"));
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator(".loading")).toHaveCount(0);
      await expect(page.locator(".notice-error")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        `${route} at ${width}`,
      ).toBe(true);
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(
        result.violations.map((v) => ({
          id: v.id,
          elements: v.nodes.map((n) => n.target),
        })),
      ).toEqual([]);
      if (route === "/admin")
        await page.screenshot({
          path: `/private/tmp/casa-admin-${width}.png`,
          fullPage: true,
        });
    }
    if (width === 390) {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await page.getByRole("link", { name: "Users", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "User management" }),
      ).toBeVisible();
    }
  }
});
