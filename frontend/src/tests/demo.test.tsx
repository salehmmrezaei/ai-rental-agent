import { expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { getSession, readSession, setSession } from "../api/session";
import {
  admin,
  json,
  landlord,
  mockApi,
  page,
  renderApp,
  tenant,
} from "./helpers";
import type { Role, User } from "../api/types";

const demoStatus = {
  enabled: true,
  read_only: true,
  assistant_mode: "simulated",
  roles: ["tenant", "landlord", "admin"],
};
const personas: Record<Role, User> = { tenant, landlord, admin };

function demoSession() {
  setSession({
    token: "visitor-token",
    expiresAt: Date.now() + 3600000,
    demo: true,
  });
}

it("offers password-free demo roles and switches workspaces with per-tab sessions", async () => {
  let current: User | undefined;
  const { calls } = mockApi(undefined, (path, method, body) => {
    if (path === "/demo/status") return json(demoStatus);
    if (path === "/demo/access" && method === "POST") {
      current = personas[body.role as Role];
      return json({
        user: current,
        access_token: `demo-${current.role}`,
        expires_in: 1800,
      });
    }
  });
  renderApp("/register");
  await screen.findByRole("heading", { name: "Explore Casa." });
  expect(screen.queryByLabelText("Email address")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Explore Tenant" }));
  await screen.findByRole("heading", { name: /Welcome back/ });
  expect(screen.getByText("Tenant workspace")).toBeInTheDocument();
  expect(localStorage.getItem("casa.session")).toBeNull();
  expect(JSON.parse(sessionStorage.getItem("casa.demo.session")!).token).toBe(
    "demo-tenant",
  );
  expect(readSession()?.demo).toBe(true);
  await user.click(screen.getByRole("button", { name: "Explore Agency" }));
  await screen.findByText("Agency workspace");
  expect(screen.queryByText("Tenant workspace")).not.toBeInTheDocument();
  expect(getSession()?.token).toBe("demo-admin");
  expect(
    calls.filter((c) => c.path === "/demo/access").map((c) => c.body.role),
  ).toEqual(["tenant", "admin"]);
  expect(calls.some((c) => c.path.startsWith("/auth/"))).toBe(false);
});

it("keeps demo access errors visible without storing a failed session", async () => {
  mockApi(undefined, (path) =>
    path === "/demo/status"
      ? json(demoStatus)
      : path === "/demo/access"
        ? json(
            { error: { message: "Please try this role again shortly." } },
            429,
          )
        : undefined,
  );
  renderApp("/login");
  await screen.findByRole("heading", { name: "Explore Casa." });
  await userEvent.click(
    screen.getByRole("button", { name: "Explore Landlord" }),
  );
  await screen.findByText("Please try this role again shortly.");
  expect(getSession()).toBeNull();
});

it("shows shared profiles without allowing account or password changes", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/demo/status" ? json(demoStatus) : undefined,
  );
  demoSession();
  renderApp("/tenant/profile");
  await screen.findByRole("heading", { name: "Tenant profile" });
  await screen.findByRole("complementary", {
    name: "Fictional portfolio demo",
  });
  expect(screen.getByLabelText("Full name")).toBeDisabled();
  expect(screen.getByLabelText("Email address")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save details" })).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Update password" }),
  ).toBeDisabled();
  expect(calls.some((c) => c.method !== "GET")).toBe(false);
});

it("disables agency decisions while retaining queue filters", async () => {
  const { calls } = mockApi(admin, (path) => {
    if (path === "/demo/status") return json(demoStatus);
    if (path === "/admin/applications")
      return json(
        page([
          {
            id: "application-id",
            status: "submitted",
            property_title: "Synthetic home",
            unit_name: "Room A",
            start_date: "2027-01-01",
            end_date: "2027-03-01",
          },
        ]),
      );
  });
  demoSession();
  renderApp("/admin/applications");
  await screen.findByRole("button", { name: "Start review" });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Start review" })).toBeDisabled(),
  );
  expect(
    screen.getByRole("button", { name: "Approve & create contract" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  expect(screen.getByLabelText("Application status")).toBeEnabled();
  expect(calls.some((c) => c.method !== "GET")).toBe(false);
});

it("explains a direct property-editor link without exposing an upload or create form", async () => {
  mockApi(landlord, (path) =>
    path === "/demo/status" ? json(demoStatus) : undefined,
  );
  demoSession();
  renderApp("/landlord/properties/new");
  await screen.findByRole("heading", { name: "Add a property" });
  expect(screen.queryByLabelText("Property title")).not.toBeInTheDocument();
  expect(screen.getAllByText(/Read-only demo:/).length).toBeGreaterThan(0);
});

it("labels offline chat honestly and sends a supported query with no API-key setup UI", async () => {
  const reply = {
    id: "demo-thread",
    title: "Sample rentals",
    updated_at: "2026-11-17T12:00:00Z",
    messages: [
      {
        id: "answer",
        role: "assistant",
        content: "You have one sample application.",
        listings: [],
        actions: [],
        created_at: "2026-11-17T12:00:00Z",
      },
    ],
  };
  const { calls } = mockApi(tenant, (path) => {
    if (path === "/demo/status") return json(demoStatus);
    if (path === "/assistant/status")
      return json({
        available: true,
        mode: "simulated",
        message: "Simulated AI Assistant",
      });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat" || path === "/assistant/threads/demo-thread")
      return json(reply);
  });
  demoSession();
  renderApp("/tenant/assistant");
  await screen.findByRole("heading", { name: "Simulated AI Assistant" });
  expect(screen.queryByText(/sent to OpenAI/)).not.toBeInTheDocument();
  expect(screen.queryByText(/not configured/)).not.toBeInTheDocument();
  const user = userEvent.setup();
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Show my applications." }),
    ).toBeEnabled(),
  );
  await user.click(
    screen.getByRole("button", { name: "Show my applications." }),
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("You have one sample application.");
  expect(calls.find((c) => c.path === "/assistant/chat")?.body.message).toBe(
    "Show my applications.",
  );
  expect(calls.every((c) => c.url.origin === "http://localhost")).toBe(true);
});

it("keeps Blu and labels the popup simulation", async () => {
  mockApi(tenant, (path) => {
    if (path === "/demo/status") return json(demoStatus);
    if (path === "/assistant/status")
      return json({ available: true, mode: "simulated" });
    if (path === "/assistant/threads") return json([]);
  });
  demoSession();
  renderApp("/tenant");
  await screen.findByRole("complementary", {
    name: "Fictional portfolio demo",
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Blu assistant" });
  await within(dialog).findByText(/Simulated AI Assistant · Sample data only/);
  expect(within(dialog).getByLabelText("Message Blu")).toBeEnabled();
});

it("does not let another tab's normal-login storage event replace a demo session", async () => {
  mockApi(tenant, (path) =>
    path === "/demo/status" ? json(demoStatus) : undefined,
  );
  demoSession();
  renderApp("/tenant");
  await screen.findByRole("complementary", {
    name: "Fictional portfolio demo",
  });
  localStorage.setItem(
    "casa.session",
    JSON.stringify({ token: "another-tab", expiresAt: Date.now() + 3600000 }),
  );
  window.dispatchEvent(new StorageEvent("storage", { key: "casa.session" }));
  expect(getSession()?.token).toBe("visitor-token");
});

it("fails closed when mode settings cannot load and allows retry", async () => {
  let failed = true;
  mockApi(undefined, (path) =>
    path === "/demo/status"
      ? failed
        ? json({ error: { message: "Unavailable" } }, 503)
        : json(demoStatus)
      : undefined,
  );
  renderApp("/register");
  await screen.findByRole("button", { name: "Retry loading Casa" });
  expect(screen.queryByLabelText("Email address")).not.toBeInTheDocument();
  failed = false;
  await userEvent.click(
    screen.getByRole("button", { name: "Retry loading Casa" }),
  );
  await screen.findByRole("heading", { name: "Explore Casa." });
});
