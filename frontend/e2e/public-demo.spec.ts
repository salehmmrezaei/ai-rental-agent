import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

async function enter(page: Page, role: "Tenant" | "Landlord" | "Agency") {
  await page.goto("/login");
  await page
    .getByRole("button", { name: `Explore ${role}`, exact: true })
    .click();
  await expect(
    page.getByText(`${role} workspace`, { exact: true }),
  ).toBeVisible();
}

test("sample homes, images and React deep links work without signing in", async ({
  page,
}) => {
  await page.goto("/listings");
  await expect(
    page.getByRole("complementary", { name: "Fictional portfolio demo" }),
  ).toBeVisible();
  const photo = page.locator(".listing-card .listing-photo").first();
  await expect(photo).toBeVisible();
  await expect(photo.locator("img")).toBeVisible();
  await expect
    .poll(() =>
      photo
        .locator("img")
        .evaluate((img: HTMLImageElement) => img.naturalWidth),
    )
    .toBeGreaterThan(0);
  await photo.click();
  await expect(page).toHaveURL(/\/listings\/[a-f0-9-]+$/);
  const title = await page.locator("h1").textContent();
  await page.reload();
  await expect(page.locator("h1")).toHaveText(title!);
  await expect(
    page.getByRole("button", { name: "Save home", exact: true }),
  ).toBeDisabled();
});

test("all three roles can be explored while profile, inventory and administration stay read-only", async ({
  page,
}) => {
  await enter(page, "Tenant");
  await page.goto("/tenant/profile");
  await expect(page.getByLabel("Email address")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Update password" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Explore Landlord", exact: true })
    .click();
  await expect(
    page.getByText("Landlord workspace", { exact: true }),
  ).toBeVisible();
  await page.goto("/landlord/properties");
  await expect(
    page.getByRole("button", { name: "Add property", exact: true }),
  ).toBeDisabled();
  await page.locator(".property-card .property-cover").first().click();
  await expect(
    page.getByRole("button", { name: "Edit property", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /^Pictures/ }).click();
  await expect(
    page.getByRole("button", { name: "Upload photo", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Explore Agency", exact: true })
    .click();
  await expect(
    page.getByText("Agency workspace", { exact: true }),
  ).toBeVisible();
  await page.goto("/admin/users");
  await expect(
    page.getByRole("button", { name: /^Edit / }).first(),
  ).toBeDisabled();
  await page.goto("/admin/applications");
  await expect(
    page.getByRole("button", { name: "Approve & create contract" }).first(),
  ).toBeDisabled();
});

test("the simulated assistant and Blu return listing cards without an API key", async ({
  page,
  baseURL,
}) => {
  const externalRequests: string[] = [];
  const expectedOrigin = new URL(baseURL!).origin;
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).origin !== expectedOrigin
    )
      externalRequests.push(request.url());
  });
  await enter(page, "Tenant");
  await page.goto("/tenant/assistant");
  await expect(
    page.getByRole("heading", { name: "Simulated AI Assistant", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Find rooms in Bologna under €700/month.",
      exact: true,
    })
    .click();
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".assistant-home").first()).toBeVisible();
  await expect(page.getByText(/not configured yet/)).toHaveCount(0);
  await page
    .getByRole("button", { name: "Open Blu assistant", exact: true })
    .click();
  const blu = page.getByRole("dialog", { name: "Blu assistant" });
  await expect(
    blu.getByText(/Simulated AI Assistant · Sample data only/),
  ).toBeVisible();
  await blu.getByLabel("Message Blu").fill("Show my applications.");
  await blu
    .getByRole("button", { name: "Send request to Blu", exact: true })
    .click();
  await expect(blu.locator(".assistant-message:not(.own)")).toHaveCount(1);
  expect(externalRequests).toEqual([]);
});

test("direct API writes cannot bypass demo restrictions and visitor chat histories are isolated", async ({
  browser,
  page,
}) => {
  await enter(page, "Tenant");
  const session = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("casa.demo.session")!),
  );
  const headers = { Authorization: `Bearer ${session.token}` };
  const registration = await page.request.post("/api/v1/auth/register", {
    data: {
      full_name: "Synthetic Visitor",
      email: "visitor@example.com",
      password: "synthetic-password-123",
      role: "tenant",
    },
  });
  expect(registration.status()).toBe(403);
  const profile = await page.request.patch("/api/v1/users/me", {
    headers,
    data: { full_name: "Changed" },
  });
  expect(profile.status()).toBe(403);
  const chat = await page.request.post("/api/v1/assistant/chat", {
    headers,
    data: { message: "Show my applications." },
  });
  expect(chat.ok()).toBe(true);
  const ownThreads = await page.request.get("/api/v1/assistant/threads", {
    headers,
  });
  expect((await ownThreads.json()).length).toBeGreaterThan(0);
  const second = await browser.newContext({ baseURL: new URL(page.url()).origin });
  try {
    const other = await second.newPage();
    await enter(other, "Tenant");
    const otherSession = await other.evaluate(() =>
      JSON.parse(sessionStorage.getItem("casa.demo.session")!),
    );
    const threads = await other.request.get("/api/v1/assistant/threads", {
      headers: { Authorization: `Bearer ${otherSession.token}` },
    });
    expect(await threads.json()).toEqual([]);
  } finally {
    await second.close();
  }
});

test("the demo role guide remains accessible on desktop and mobile", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "Explore Casa." }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Explore Agency", exact: true }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
});
