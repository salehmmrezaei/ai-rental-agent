import { expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { json, mockApi, renderApp, tenant, landlord, admin } from "./helpers";
import type { AssistantThreadDetail, AssistantAction } from "../api/assistant";

const action: AssistantAction = {
  id: "action-id",
  kind: "apply",
  summary: "Apply for Bologna Room A, 2027-01-01 to 2027-03-01.",
  payload: {
    listing_id: "listing-id",
    start_date: "2027-01-01",
    end_date: "2027-03-01",
    note: "A quiet place to study",
  },
  status: "pending",
  expires_at: new Date(Date.now() + 600000).toISOString(),
  result: null,
};
function thread(actions: AssistantAction[] = []): AssistantThreadDetail {
  return {
    id: "chat-id",
    title: "Find me a room",
    updated_at: "2026-10-13T10:00:00Z",
    messages: [
      {
        id: "user-msg",
        role: "user",
        content: "Find me a room",
        listings: [],
        actions: [],
        created_at: "2026-10-13T10:00:00Z",
      },
      {
        id: "assistant-msg",
        role: "assistant",
        content: "Review your dates and confirm when ready.",
        listings: [
          {
            id: "listing-id",
            title: "Bologna home",
            city: "Bologna",
            kind: "room",
            unit_name: "Room A",
            monthly_rent: "650.00",
            available_now: true,
          },
        ],
        actions,
        created_at: "2026-10-13T10:00:01Z",
      },
    ],
  };
}

it("shows setup state while leaving ordinary browsing available", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({
          available: false,
          message: "The AI assistant is not configured yet.",
        })
      : path === "/assistant/threads"
        ? json([])
        : undefined,
  );
  renderApp("/tenant/assistant");
  await screen.findByText("The AI assistant is not configured yet.");
  expect(screen.getByLabelText("Message the assistant")).toBeDisabled();
  expect(
    screen.getByRole("link", { name: "Browse all homes" }),
  ).toHaveAttribute("href", "/listings");
  expect(calls.some((c) => c.path === "/assistant/chat")).toBe(false);
});

it("sends only the current message and server thread ID; shows real listing references", async () => {
  let current: AssistantThreadDetail | undefined;
  const { calls } = mockApi(tenant, (path, method) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json(current ? [current] : []);
    if (path === "/assistant/chat" && method === "POST") {
      current = thread();
      return json(current);
    }
    if (path === "/assistant/threads/chat-id") return json(current);
  });
  renderApp("/tenant/assistant");
  const user = userEvent.setup();
  await waitFor(() =>
    expect(screen.getByLabelText("Message the assistant")).toBeEnabled(),
  );
  await user.type(
    screen.getByLabelText("Message the assistant"),
    "Find me a room",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Review your dates and confirm when ready.");
  expect(calls.find((c) => c.path === "/assistant/chat")?.body).toEqual({
    message: "Find me a room",
    thread_id: null,
  });
  expect(screen.getByRole("link", { name: /Bologna home/ })).toHaveAttribute(
    "href",
    "/listings/listing-id",
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled(),
  );
  await user.click(screen.getByRole("button", { name: "New chat" }));
  await waitFor(() =>
    expect(
      screen.queryByText("Review your dates and confirm when ready."),
    ).not.toBeInTheDocument(),
  );
});

it("sends once on Enter and clears the textbox before the reply arrives", async () => {
  let finish!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const current = thread();
  const { calls } = mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return response;
    if (path === "/assistant/threads/chat-id") return json(current);
  });
  renderApp("/tenant/assistant");
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Message the assistant");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Find me a room{Enter}");
  expect(input).toHaveValue("");
  expect(input).toBeDisabled();
  expect(
    within(screen.getByRole("log")).getByText("Find me a room"),
  ).toBeInTheDocument();
  await user.keyboard("{Enter}");
  expect(calls.filter((call) => call.path === "/assistant/chat")).toHaveLength(
    1,
  );
  expect(calls.find((call) => call.path === "/assistant/chat")?.body).toEqual({
    message: "Find me a room",
    thread_id: null,
  });
  finish(json(current));
  await screen.findByText("Review your dates and confirm when ready.");
  expect(screen.getByLabelText("Message the assistant")).toHaveValue("");
});

it("keeps Shift+Enter newlines and composing Enter out of message submission", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : undefined,
  );
  renderApp("/tenant/assistant");
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Message the assistant");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Find a room");
  await user.keyboard("{Shift>}{Enter}{/Shift}");
  await user.type(input, "In Bologna");
  expect(input).toHaveValue("Find a room\nIn Bologna");
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(calls.some((call) => call.path === "/assistant/chat")).toBe(false);
  expect(input).toHaveValue("Find a room\nIn Bologna");
});

it("requires a separate click to confirm and displays the exact proposed payload", async () => {
  const current = thread([action]);
  const { calls } = mockApi(tenant, (path, method) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/chat-id") return json(current);
    if (path === "/assistant/actions/action-id/confirm" && method === "POST")
      return json({
        ...action,
        status: "confirmed",
        result: { id: "application-id" },
      });
  });
  renderApp("/tenant/assistant?chat=chat-id");
  await screen.findByRole("button", { name: "Confirm action" });
  expect(screen.getByText("A quiet place to study")).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Confirm action" }));
  await screen.findByText("Action completed");
  expect(calls.find((c) => c.path.endsWith("/confirm"))?.body).toEqual({
    confirmed: true,
  });
  expect(
    screen.getByRole("link", { name: "View applications" }),
  ).toHaveAttribute("href", "/tenant/applications");
});

it("lets the tenant dismiss a proposal and prevents expired confirmations", async () => {
  const expired = {
    ...action,
    id: "expired-id",
    expires_at: "2020-01-01T00:00:00Z",
  };
  const current = thread([action, expired]);
  const { calls } = mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([current])
        : path === "/assistant/threads/chat-id"
          ? json(current)
          : path === "/assistant/actions/action-id/cancel"
            ? json({ ...action, status: "cancelled" })
            : undefined,
  );
  renderApp("/tenant/assistant?chat=chat-id");
  await screen.findByText("This proposal expired. Ask for a new one.");
  expect(
    screen.getAllByRole("button", { name: "Confirm action" })[1],
  ).toBeDisabled();
  await userEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]);
  await screen.findByText("Action dismissed");
  expect(calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
});

it("preserves the message draft after an AI failure", async () => {
  mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : path === "/assistant/chat"
          ? json(
              {
                error: {
                  code: "assistant_timeout",
                  message: "The AI assistant is temporarily unavailable.",
                },
              },
              503,
            )
          : undefined,
  );
  renderApp("/tenant/assistant");
  await waitFor(() =>
    expect(screen.getByLabelText("Message the assistant")).toBeEnabled(),
  );
  await userEvent.type(
    screen.getByLabelText("Message the assistant"),
    "Find a room",
  );
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Message the assistant")).toHaveValue(
    "Find a room",
  );
});

it("renders model text as text so HTML and external links cannot execute", async () => {
  const current = thread();
  current.messages[1].content =
    "<img src=x onerror=alert(1)> [Click](https://evil.example)";
  mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([current])
        : path === "/assistant/threads/chat-id"
          ? json(current)
          : undefined,
  );
  renderApp("/tenant/assistant?chat=chat-id");
  await screen.findByText(current.messages[1].content);
  expect(document.querySelector('a[href="https://evil.example"]')).toBeNull();
  expect(document.querySelector('img[src="x"]')).toBeNull();
});

for (const user of [landlord, admin]) {
  it(`keeps the tenant assistant out of the ${user.role} workspace`, async () => {
    const { calls } = mockApi(user);
    renderApp("/tenant/assistant");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "AI assistant" })).toHaveAttribute(
      "href",
      `/${user.role}/assistant`,
    );
    expect(calls.some((c) => c.path.startsWith("/assistant"))).toBe(false);
  });
}

it.each([admin, landlord])(
  "handles $role requests and reviews exact property changes",
  async (manager) => {
    const agencyAction: AssistantAction = {
      ...action,
      kind: "update_unit",
      summary: "Update Bologna home · Room A.",
      payload: {
        unit_id: "unit-id",
        monthly_rent: "725.00",
        deposit: "0",
        amenities: [],
        area_sqm: null,
      },
    };
    let current: AssistantThreadDetail | undefined;
    const { calls } = mockApi(manager, (path, method) => {
      if (path === "/assistant/status") return json({ available: true });
      if (path === "/assistant/threads") return json(current ? [current] : []);
      if (path === "/assistant/chat" && method === "POST") {
        current = thread([agencyAction]);
        current.title = "Set Room A rent to 725 euros";
        current.messages[1].listings = [];
        return json(current);
      }
      if (path === "/assistant/threads/chat-id") return json(current);
      if (path === "/assistant/actions/action-id/confirm")
        return json({
          ...agencyAction,
          status: "confirmed",
          result: { id: "unit-id" },
        });
    });
    renderApp(`/${manager.role}/assistant`);
    await screen.findByRole("heading", {
      name:
        manager.role === "admin"
          ? "AI agency assistant"
          : "AI landlord assistant",
    });
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByLabelText("Message the assistant")).toBeEnabled(),
    );
    await user.type(
      screen.getByLabelText("Message the assistant"),
      "Set Room A rent to 725 euros",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(agencyAction.summary);
    expect(screen.getByRole("link", { name: "AI assistant" })).toHaveAttribute(
      "href",
      `/${manager.role}/assistant`,
    );
    expect(
      screen.getByRole("button", { name: "Set Room A rent to 725 euros" }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("€725.00 / month")).toBeInTheDocument();
    expect(screen.getByText("€0.00")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm action" }));
    await screen.findByText("Action completed");
    expect(
      within(
        screen.getByRole("region", { name: "Review proposed action" }),
      ).getByRole("link", { name: "View properties" }),
    ).toHaveAttribute("href", `/${manager.role}/properties`);
    expect(calls.find((c) => c.path.endsWith("/confirm"))?.body).toEqual({
      confirmed: true,
    });
  },
);

it("prefills a landlord's managed property reference without sending it automatically", async () => {
  const id = "00000000-0000-4000-8000-000000000003";
  const { calls } = mockApi(landlord, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : undefined,
  );
  renderApp(`/landlord/assistant?property=${id}`);
  await screen.findByRole("heading", { name: "AI landlord assistant" });
  expect(screen.getByLabelText("Message the assistant")).toHaveValue(
    `Show me this property's units, listings and rental status (property ID ${id}).`,
  );
  expect(screen.getByRole("link", { name: "View properties" })).toHaveAttribute(
    "href",
    "/landlord/properties",
  );
  expect(calls.some((call) => call.path === "/assistant/chat")).toBe(false);
});
