import { beforeEach, expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AssistantThreadDetail, AssistantAction } from "../api/assistant";
import { mockApi, renderApp, tenant, landlord, admin, json } from "./helpers";

const chatId = "00000000-0000-4000-8000-000000000001";
const listingId = "00000000-0000-4000-8000-000000000002";
const action: AssistantAction = {
  id: "action-id",
  kind: "contact_agency",
  status: "pending",
  summary: "Ask the agency about utilities for Bologna Room A.",
  payload: {
    subject: "Bologna Room A",
    initial_message: "Are utilities included in the rent?",
  },
  expires_at: new Date(Date.now() + 600000).toISOString(),
  result: null,
};
function thread(actions: AssistantAction[] = []): AssistantThreadDetail {
  return {
    id: chatId,
    title: "Ask about utilities",
    updated_at: "2026-10-13T10:00:00Z",
    messages: [
      {
        id: "user-msg",
        role: "user",
        content: "Ask about utilities",
        created_at: "2026-10-13T10:00:00Z",
        listings: [],
        actions: [],
      },
      {
        id: "reply-msg",
        role: "assistant",
        content: "I prepared your agency message. Review it first.",
        created_at: "2026-10-13T10:00:01Z",
        listings: [],
        actions,
      },
    ],
  };
}
beforeEach(() => {
  localStorage.removeItem("casa:companion:v1");
  sessionStorage.clear();
});

it("opens tenant chat from any page and sends orders without navigating", async () => {
  let current: AssistantThreadDetail | undefined;
  const { calls } = mockApi(tenant, (path, method) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json(current ? [current] : []);
    if (path === "/assistant/chat" && method === "POST") {
      current = thread([action]);
      return json(current);
    }
    if (path === `/assistant/threads/${chatId}`) return json(current);
    if (path === "/assistant/actions/action-id/confirm")
      return json({
        ...action,
        status: "confirmed",
        result: { id: "message-id" },
      });
  });
  renderApp("/");
  expect(calls.some((c) => c.path.startsWith("/assistant"))).toBe(false);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const dialog = await screen.findByRole("dialog", { name: "Blu assistant" });
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Message Blu")).toBeEnabled(),
  );
  await user.type(
    within(dialog).getByLabelText("Message Blu"),
    "Ask about utilities",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Send request to Blu" }),
  );
  await within(dialog).findByText(
    "I prepared your agency message. Review it first.",
  );
  expect(calls.find((c) => c.path === "/assistant/chat")?.body).toEqual({
    message: "Ask about utilities",
    thread_id: null,
  });
  expect(
    within(dialog).getByText("Are utilities included in the rent?"),
  ).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
  await user.click(
    within(dialog).getByRole("button", { name: "Confirm action" }),
  );
  await within(dialog).findByText("Action completed");
  expect(calls.find((c) => c.path.endsWith("/confirm"))?.body).toEqual({
    confirmed: true,
  });
  expect(
    screen.getByRole("heading", { name: /Your next chapter/ }),
  ).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Close Blu" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  expect(screen.getByText("Action completed")).toBeInTheDocument();
});

it("sends once on Enter and clears Blu's textbox before the reply arrives", async () => {
  let finish!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const current = thread();
  const { calls } = mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return response;
    if (path === `/assistant/threads/${chatId}`) return json(current);
  });
  renderApp("/");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const input = await screen.findByLabelText("Message Blu");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Ask about utilities{Enter}");
  expect(input).toHaveValue("");
  expect(input).toBeDisabled();
  expect(
    within(screen.getByRole("log")).getByText("Ask about utilities"),
  ).toBeInTheDocument();
  await user.keyboard("{Enter}");
  expect(calls.filter((call) => call.path === "/assistant/chat")).toHaveLength(
    1,
  );
  expect(calls.find((call) => call.path === "/assistant/chat")?.body).toEqual({
    message: "Ask about utilities",
    thread_id: null,
  });
  finish(json(current));
  await screen.findByText("I prepared your agency message. Review it first.");
  expect(screen.getByLabelText("Message Blu")).toHaveValue("");
});

it("keeps Shift+Enter newlines and composing Enter out of Blu submissions", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : undefined,
  );
  renderApp("/");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const input = await screen.findByLabelText("Message Blu");
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

it("adds the currently viewed home's ID to a tenant's request", async () => {
  const { listing } = await import("./helpers");
  const { calls } = mockApi(tenant, (path) =>
    path === `/listings/${listingId}`
      ? json({ ...listing, id: listingId })
      : path === "/assistant/status"
        ? json({ available: true })
        : path === "/assistant/threads"
          ? json([])
          : path === "/assistant/chat" ||
              path === `/assistant/threads/${chatId}`
            ? json(thread())
            : undefined,
  );
  renderApp(`/listings/${listingId}`);
  await screen.findByRole("heading", { name: listing.title });
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Message Blu")).toBeEnabled(),
  );
  await userEvent.type(
    screen.getByLabelText("Message Blu"),
    "Are utilities included?",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Send request to Blu" }),
  );
  await screen.findByText("I prepared your agency message. Review it first.");
  expect(calls.find((c) => c.path === "/assistant/chat")?.body.message).toBe(
    `Are utilities included?\n\nCurrent home listing ID: ${listingId}`,
  );
});

it("restores only the signed-in tenant's selected conversation", async () => {
  sessionStorage.setItem(`casa:blu-chat:${tenant.id}`, chatId);
  sessionStorage.setItem(
    "casa:blu-chat:other-tenant",
    "11111111-1111-4111-8111-111111111111",
  );
  const current = thread();
  const { calls } = mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([current])
        : path === `/assistant/threads/${chatId}`
          ? json(current)
          : undefined,
  );
  renderApp("/tenant");
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await screen.findByText("I prepared your agency message. Review it first.");
  expect(calls.some((c) => c.path.includes("11111111"))).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "New Blu chat" }));
  expect(
    screen.queryByText("I prepared your agency message. Review it first."),
  ).not.toBeInTheDocument();
  expect(sessionStorage.getItem(`casa:blu-chat:${tenant.id}`)).toBeNull();
});

it("keeps failed drafts and shows configuration errors inside the popup", async () => {
  mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : path === "/assistant/chat"
          ? json(
              { error: { message: "Assistant temporarily unavailable" } },
              503,
            )
          : undefined,
  );
  renderApp("/");
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Message Blu")).toBeEnabled(),
  );
  await userEvent.type(screen.getByLabelText("Message Blu"), "Find a room");
  await userEvent.click(
    screen.getByRole("button", { name: "Send request to Blu" }),
  );
  await screen.findByText("Assistant temporarily unavailable");
  expect(screen.getByLabelText("Message Blu")).toHaveValue("Find a room");
});

it("lets landlords prepare and confirm property changes from Blu", async () => {
  const landlordAction: AssistantAction = {
    ...action,
    kind: "update_unit",
    summary: "Update Bologna home · Room A.",
    payload: { unit_id: "unit-id", monthly_rent: "725.00" },
  };
  const current = thread([landlordAction]);
  current.messages[1].content = "Review your room's new rent.";
  const { calls } = mockApi(landlord, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : path === "/assistant/chat" || path === `/assistant/threads/${chatId}`
          ? json(current)
          : path === "/assistant/actions/action-id/confirm"
            ? json({
                ...landlordAction,
                status: "confirmed",
                result: { id: "unit-id" },
              })
            : undefined,
  );
  renderApp("/landlord");
  await screen.findByRole("heading", { name: /Welcome back/ });
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await screen.findByText(/Your property helper/);
  await waitFor(() =>
    expect(screen.getByLabelText("Message Blu")).toBeEnabled(),
  );
  await userEvent.type(
    screen.getByLabelText("Message Blu"),
    "Set Room A rent to 725 euros",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Send request to Blu" }),
  );
  await screen.findByText(landlordAction.summary);
  expect(screen.getByText("€725.00 / month")).toBeInTheDocument();
  expect(calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Confirm action" }));
  await screen.findByText("Action completed");
  expect(screen.getByRole("link", { name: "View properties" })).toHaveAttribute(
    "href",
    "/landlord/properties",
  );
  await userEvent.click(screen.getByRole("tab", { name: "Activities" }));
  await userEvent.click(screen.getByRole("button", { name: "Pet Blu" }));
  expect(document.querySelector(".companion-walker")).toHaveAttribute(
    "data-activity",
    "pet",
  );
});

it("lets agency admins send requests from Blu", async () => {
  const current = thread();
  const { calls } = mockApi(admin, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([])
        : path === "/assistant/chat" || path === `/assistant/threads/${chatId}`
          ? json(current)
          : undefined,
  );
  renderApp("/admin");
  await screen.findByRole("heading", { name: /Welcome back/ });
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  await screen.findByText(/Your agency helper/);
  await user.click(
    screen.getByRole("button", { name: "Show requested visits." }),
  );
  await user.click(screen.getByRole("button", { name: "Send request to Blu" }));
  await screen.findByText("I prepared your agency message. Review it first.");
  expect(calls.find((c) => c.path === "/assistant/chat")?.body).toEqual({
    message: "Show requested visits.",
    thread_id: null,
  });
});

it("requires sign-in before sending requests from a public page", async () => {
  const { calls } = mockApi();
  renderApp("/");
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await screen.findByRole("link", { name: "Sign in to chat" });
  expect(screen.queryByLabelText("Message Blu")).not.toBeInTheDocument();
  expect(calls.some((c) => c.path.startsWith("/assistant"))).toBe(false);
});

it("clears private popup messages when the tenant signs out", async () => {
  sessionStorage.setItem(`casa:blu-chat:${tenant.id}`, chatId);
  const current = thread();
  mockApi(tenant, (path) =>
    path === "/assistant/status"
      ? json({ available: true })
      : path === "/assistant/threads"
        ? json([current])
        : path === `/assistant/threads/${chatId}`
          ? json(current)
          : path === "/auth/logout"
            ? json(null, 204)
            : undefined,
  );
  renderApp("/tenant");
  await screen.findByRole("heading", { name: /Welcome back/ });
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await screen.findByText("I prepared your agency message. Review it first.");
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByLabelText("Email address");
  await userEvent.click(
    screen.getByRole("button", { name: "Open Blu assistant" }),
  );
  await screen.findByRole("link", { name: "Sign in to chat" });
  expect(
    screen.queryByText("I prepared your agency message. Review it first."),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Message Blu")).not.toBeInTheDocument();
});
