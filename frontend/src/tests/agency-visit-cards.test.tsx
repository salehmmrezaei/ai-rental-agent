import { beforeEach, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AssistantThreadDetail, AssistantVisit } from "../api/assistant";
import type { Visit } from "../api/types";
import { admin, json, mockApi, page, renderApp } from "./helpers";

const searchPath =
  "/assistant/threads/visit-chat/messages/visit-message/visits";
function visits(start = 1, count = 6): AssistantVisit[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `visit-${start + index}`,
    property_title: `Bologna home ${start + index}`,
    unit_name: `Room ${start + index}`,
    tenant_name: `Demo tenant ${start + index}`,
    status: "requested",
    requested_at: "2030-01-08T13:00:00Z",
    scheduled_at: null,
    duration_minutes: 30,
    note: `I would like to visit room ${start + index}.`,
  }));
}
function visitThread(total = 21): AssistantThreadDetail {
  return {
    id: "visit-chat",
    title: "Visits waiting to be scheduled",
    updated_at: "2026-11-03T10:00:00Z",
    messages: [
      {
        id: "visit-message",
        role: "assistant",
        content:
          "There are 21 visit requests waiting to be scheduled. I'm showing the first 6.",
        listings: [],
        visit_search: {
          items: visits(1, Math.min(total, 6)),
          page: 1,
          page_size: 6,
          total,
          cards_only: true,
        },
        actions: [],
        created_at: "2026-11-03T10:00:00Z",
      },
    ],
  };
}
beforeEach(() => sessionStorage.clear());

it("shows the actual six requests behind the 21-count and opens the exact visit for confirmed scheduling", async () => {
  const current = visitThread();
  let selected: Visit = {
    ...visits()[0],
    tenant_id: "tenant-id",
    rental_unit_id: "room-id",
    property_id: "property-id",
    scheduled_end_at: null,
    agency_note: null,
    assigned_admin_id: null,
  };
  const { calls } = mockApi(admin, (path, method, body) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/visit-chat") return json(current);
    if (path === "/visits/visit-1") return json(selected);
    if (path === "/admin/users") return json(page([admin]));
    if (path === "/admin/visits/visit-1" && method === "PATCH") {
      selected = { ...selected, ...body };
      return json(selected);
    }
  });
  renderApp("/admin/assistant?chat=visit-chat");
  await screen.findByText("21 visit requests");
  const log = screen.getByRole("log");
  const cards = within(log).getAllByRole("link", { name: /Bologna home/ });
  expect(cards).toHaveLength(6);
  expect(cards[0]).toHaveAttribute("href", "/admin/visits?visit=visit-1");
  expect(cards[0]).toHaveTextContent("Demo tenant 1");
  expect(cards[0]).toHaveTextContent("Room 1");
  expect(cards[0]).toHaveTextContent("I would like to visit room 1.");
  expect(cards[0]).toHaveTextContent("Europe/Rome");
  expect(
    screen.queryByText(/There are 21 visit requests/),
  ).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(cards[0]);
  await screen.findByRole("heading", { name: "Review visit" });
  await screen.findByRole("heading", { name: "Bologna home 1" });
  expect(screen.getByText("Tenant: Demo tenant 1")).toBeInTheDocument();
  expect(calls.some((call) => call.path === "/visits")).toBe(false);
  expect(calls.every((call) => call.method === "GET")).toBe(true);
  await user.click(screen.getByRole("button", { name: "Schedule visit" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Schedule a visit",
  });
  await within(dialog).findByLabelText("Assigned agent");
  expect(calls.some((call) => call.method === "PATCH")).toBe(false);
  await user.click(
    within(dialog).getByRole("button", { name: "Confirm schedule" }),
  );
  await screen.findByText("Visit updated.");
  await screen.findByRole("button", { name: "Reschedule" });
  const writes = calls.filter((call) => call.method === "PATCH");
  expect(writes).toHaveLength(1);
  expect(writes[0].path).toBe("/admin/visits/visit-1");
  expect(writes[0].body).toMatchObject({
    status: "scheduled",
    duration_minutes: 30,
    assigned_admin_id: admin.id,
  });
});

it("shows visit cards in Blu, pages without a model call, and preserves the visible page for followups", async () => {
  const current = visitThread();
  const { calls } = mockApi(admin, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return json(current);
    if (path === "/assistant/threads/visit-chat") return json(current);
    if (path === searchPath)
      return json({ items: visits(7), page: 2, page_size: 6, total: 21 });
  });
  renderApp("/admin");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const dialog = await screen.findByRole("dialog", { name: "Blu assistant" });
  const input = within(dialog).getByLabelText("Message Blu");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Show me visit requests waiting to be scheduled.");
  await user.click(
    within(dialog).getByRole("button", { name: "Send request to Blu" }),
  );
  await within(dialog).findByText("21 visit requests");
  expect(
    within(dialog).getAllByRole("link", { name: /Bologna home/ }),
  ).toHaveLength(6);
  expect(
    within(dialog).queryByText(/There are 21 visit requests/),
  ).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Next" }));
  await within(dialog).findByRole("link", { name: /Bologna home 7/ });
  expect(within(dialog).getByText("Page 2 of 4")).toBeInTheDocument();
  expect(calls.filter((call) => call.path === "/assistant/chat")).toHaveLength(
    1,
  );
  await user.type(input, "Help me schedule the first one");
  await user.click(
    within(dialog).getByRole("button", { name: "Send request to Blu" }),
  );
  await waitFor(() =>
    expect(
      calls.filter((call) => call.path === "/assistant/chat"),
    ).toHaveLength(2),
  );
  expect(
    calls.filter((call) => call.path === "/assistant/chat")[1].body,
  ).toEqual({
    message: "Help me schedule the first one",
    thread_id: "visit-chat",
    visit_search_context: { message_id: "visit-message", page: 2 },
  });
});

it("shows the last three of 21 requests and returns to the previous page", async () => {
  const current = visitThread();
  mockApi(admin, (path, _method, _body, url) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/visit-chat") return json(current);
    if (path === searchPath) {
      const pageNumber = Number(url.searchParams.get("page"));
      return json({
        items: visits((pageNumber - 1) * 6 + 1, pageNumber === 4 ? 3 : 6),
        page: pageNumber,
        page_size: 6,
        total: 21,
      });
    }
  });
  renderApp("/admin/assistant?chat=visit-chat");
  await screen.findByText("Page 1 of 4");
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  for (const pageNumber of [2, 3, 4]) {
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText(`Page ${pageNumber} of 4`);
  }
  expect(
    within(screen.getByRole("log")).getAllByRole("link", {
      name: /Bologna home/,
    }),
  ).toHaveLength(3);
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findByText("Page 3 of 4");
  expect(
    within(screen.getByRole("log")).getAllByRole("link", {
      name: /Bologna home/,
    }),
  ).toHaveLength(6);
});

it("uses an explicit empty state when there are no matching requests", async () => {
  const current = visitThread(0);
  mockApi(admin, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/visit-chat") return json(current);
  });
  renderApp("/admin/assistant?chat=visit-chat");
  await screen.findByText("0 visit requests");
  expect(
    screen.getByText("No visit requests match this view."),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/There are 21 visit requests/),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
});

it("keeps existing visit cards on a page error and lets the agency retry", async () => {
  const current = visitThread();
  let failed = true;
  mockApi(admin, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/visit-chat") return json(current);
    if (path === searchPath)
      return failed
        ? json({ error: { message: "Visit queue unavailable" } }, 503)
        : json({ items: visits(7), page: 2, page_size: 6, total: 21 });
  });
  renderApp("/admin/assistant?chat=visit-chat");
  await screen.findByText("21 visit requests");
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Visit queue unavailable");
  expect(
    screen.getByRole("link", { name: /Bologna home 1Room/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  failed = false;
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Page 2 of 4");
  expect(screen.queryByText("Visit queue unavailable")).not.toBeInTheDocument();
});

it("does not substitute the whole queue when the selected visit is unavailable", async () => {
  const { calls } = mockApi(admin, (path) =>
    path === "/visits/missing"
      ? json({ error: { message: "Visit not found" } }, 404)
      : undefined,
  );
  renderApp("/admin/visits?visit=missing");
  await screen.findByText("Visit not found");
  expect(
    screen.getByRole("link", { name: /All visit requests/ }),
  ).toHaveAttribute("href", "/admin/visits");
  expect(calls.some((call) => call.path === "/visits")).toBe(false);
  expect(
    screen.queryByRole("button", { name: "Schedule visit" }),
  ).not.toBeInTheDocument();
});
