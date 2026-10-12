import { expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderApp, tenant, landlord, admin, json } from "./helpers";
import { safeNext } from "../pages/Auth";
import { getSession } from "../api/session";
it("redirects unauthenticated private routes without requesting private data", async () => {
  const { calls } = mockApi();
  renderApp("/tenant/applications");
  await screen.findByRole("heading", { name: "Good to see you." });
  expect(calls.some((c) => c.path === "/applications")).toBe(false);
});
it.each([tenant, landlord, admin])(
  "restores $role sessions from backend-authoritative profiles",
  async (user) => {
    mockApi(user);
    renderApp(`/${user.role}`);
    await screen.findByRole("heading", { name: /Welcome back/ });
    expect(screen.getByText(user.full_name)).toBeInTheDocument();
  },
);
it("redirects tenant attempts to access agency routes", async () => {
  const { calls } = mockApi(tenant);
  renderApp("/admin/users");
  await screen.findByRole("heading", { name: /Welcome back/ });
  expect(calls.some((c) => c.path === "/admin/users")).toBe(false);
});
it("posts sign-in and routes to the correct dashboard", async () => {
  const { calls } = mockApi(undefined, (path) =>
    path === "/auth/login"
      ? json({ user: tenant, access_token: "new-token", expires_in: 1800 })
      : undefined,
  );
  renderApp("/login");
  await screen.findByRole("heading", { name: "Good to see you." });
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email address"), tenant.email);
  await user.type(screen.getByLabelText("Password"), "synthetic-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("heading", { name: /Welcome back/ });
  expect(calls.find((c) => c.path === "/auth/login")?.body.email).toBe(
    tenant.email,
  );
  expect(getSession()?.token).toBe("new-token");
});
it("only registers tenant or landlord and signs in after persistence", async () => {
  const { calls } = mockApi(undefined, (path) =>
    path === "/auth/register"
      ? json(landlord, 201)
      : path === "/auth/login"
        ? json({ user: landlord, access_token: "new-token", expires_in: 1800 })
        : undefined,
  );
  renderApp("/register?role=landlord");
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Full name"), "Synthetic Owner");
  await user.type(screen.getByLabelText("Email address"), landlord.email);
  await user.type(screen.getByLabelText("Password"), "synthetic-password");
  expect(
    screen.queryByRole("option", { name: "admin" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByRole("heading", { name: /Welcome back/ });
  expect(calls.find((c) => c.path === "/auth/register")?.body.role).toBe(
    "landlord",
  );
});
it("clears invalid sessions", async () => {
  mockApi(tenant, (path) =>
    path === "/users/me"
      ? json({ error: { message: "Revoked" } }, 401)
      : undefined,
  );
  renderApp("/tenant");
  await screen.findByRole("heading", { name: "Good to see you." });
  expect(getSession()).toBeNull();
});
it("blocks protected content when the session cannot be verified", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/users/me"
      ? json({ error: { message: "Unavailable" } }, 503)
      : undefined,
  );
  renderApp("/tenant");
  await screen.findByRole("button", { name: "Retry session check" });
  expect(calls.some((c) => c.path === "/dashboard/statistics")).toBe(false);
});
it("revokes the server session before removing local persistence", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/auth/logout" ? json(null, 204) : undefined,
  );
  renderApp("/tenant");
  await screen.findByRole("heading", { name: /Welcome back/ });
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("heading", { name: "Good to see you." });
  expect(calls.find((c) => c.path === "/auth/logout")?.method).toBe("POST");
  expect(getSession()).toBeNull();
});
it("rejects external, protocol-relative and backslash return destinations", () => {
  for (const next of [
    "https://example.com",
    "//example.com",
    "/\\example.com",
    "/login",
  ])
    expect(safeNext(next, "tenant")).toBe("/tenant");
  expect(safeNext("/listings/123", "tenant")).toBe("/listings/123");
});
it("changes profile email with current-password verification then signs out", async () => {
  const { calls } = mockApi(tenant, (path, method) =>
    path === "/users/me" && method === "PATCH"
      ? json({ ...tenant, email: "changed@example.com" })
      : undefined,
  );
  renderApp("/tenant/profile");
  const email = await screen.findByLabelText("Email address");
  const user = userEvent.setup();
  await user.clear(email);
  await user.type(email, "changed@example.com");
  await user.type(
    screen.getByLabelText("Current password (for email changes)"),
    "synthetic-password",
  );
  await user.click(screen.getByRole("button", { name: "Save details" }));
  await screen.findByRole("heading", { name: "Good to see you." });
  expect(calls.find((c) => c.method === "PATCH")?.body.current_password).toBe(
    "synthetic-password",
  );
  expect(getSession()).toBeNull();
});
