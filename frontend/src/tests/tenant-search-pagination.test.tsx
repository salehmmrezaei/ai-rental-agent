import { beforeEach, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AssistantListing, AssistantThreadDetail } from "../api/assistant";
import { json, mockApi, renderApp, tenant } from "./helpers";

const searchPath =
  "/assistant/threads/search-chat/messages/search-message/listings";
function homes(start: number, count: number): AssistantListing[] {
  return Array.from({ length: count }, (_, offset) => ({
    id: `listing-${start + offset}`,
    title: `Bologna student home ${start + offset}`,
    city: "Bologna",
    kind: "room",
    unit_name: `Room ${start + offset}`,
    monthly_rent: "650.00",
    available_now: true,
  }));
}
function searchThread(total = 8): AssistantThreadDetail {
  return {
    id: "search-chat",
    title: "Find a university room",
    updated_at: "2026-11-03T10:00:00Z",
    messages: [
      {
        id: "search-message",
        role: "assistant",
        content:
          "1. Text-only duplicate catalogue entry. 2. Another duplicate entry.",
        listings: homes(1, Math.min(total, 6)),
        listing_search: { page: 1, page_size: 6, total, cards_only: true },
        actions: [],
        created_at: "2026-11-03T10:00:00Z",
      },
    ],
  };
}

beforeEach(() => sessionStorage.clear());

it("renders only cards, fetches Next and Previous without a model request, and sends the visible page with follow-ups", async () => {
  const current = searchThread();
  let finishPage!: (response: Response) => void;
  let deferPage = true;
  const { calls } = mockApi(tenant, (path, method, _body, url) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/search-chat") return json(current);
    if (path === searchPath) {
      if (url.searchParams.get("page") === "2") {
        if (deferPage)
          return new Promise<Response>((resolve) => {
            finishPage = resolve;
          });
        return json({ items: homes(7, 2), page: 2, page_size: 6, total: 8 });
      }
      return json({ items: homes(1, 6), page: 1, page_size: 6, total: 8 });
    }
    if (path === "/assistant/chat" && method === "POST") return json(current);
  });
  renderApp("/tenant/assistant?chat=search-chat");
  const first = await screen.findByRole("link", {
    name: /Bologna student home 1/,
  });
  expect(first).toHaveAttribute("href", "/listings/listing-1");
  expect(screen.queryByText(/Text-only duplicate/)).not.toBeInTheDocument();
  const navigation = screen.getByRole("navigation", {
    name: "Listing search pages",
  });
  expect(
    within(navigation).getByRole("button", { name: "Previous" }),
  ).toBeDisabled();
  expect(
    within(navigation).getByRole("button", { name: "Next" }),
  ).toBeEnabled();
  expect(within(navigation).getByText("Page 1 of 2")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(within(navigation).getByRole("button", { name: "Next" }));
  expect(
    within(navigation).getByRole("button", { name: "Next" }),
  ).toBeDisabled();
  expect(
    within(navigation).getByRole("button", { name: "Previous" }),
  ).toBeDisabled();
  expect(within(navigation).getByText("Loading homes…")).toBeInTheDocument();
  expect(first).toBeInTheDocument();
  finishPage(json({ items: homes(7, 2), page: 2, page_size: 6, total: 8 }));
  await screen.findByRole("link", { name: /Bologna student home 7/ });
  expect(
    screen.queryByRole("link", { name: /Bologna student home 1/ }),
  ).not.toBeInTheDocument();
  expect(
    within(navigation).getByRole("button", { name: "Next" }),
  ).toBeDisabled();
  expect(
    within(navigation).getByRole("button", { name: "Previous" }),
  ).toBeEnabled();
  expect(calls.some((call) => call.path === "/assistant/chat")).toBe(false);

  await user.click(
    within(navigation).getByRole("button", { name: "Previous" }),
  );
  await screen.findByRole("link", { name: /Bologna student home 1/ });
  expect(
    calls
      .filter((call) => call.path === searchPath)
      .map((call) => call.url.searchParams.get("page")),
  ).toEqual(["2", "1"]);
  deferPage = false;
  await user.click(within(navigation).getByRole("button", { name: "Next" }));
  await screen.findByRole("link", { name: /Bologna student home 7/ });
  await user.type(
    screen.getByLabelText("Message the assistant"),
    "Show me the first room",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() =>
    expect(calls.some((call) => call.path === "/assistant/chat")).toBe(true),
  );
  expect(calls.find((call) => call.path === "/assistant/chat")?.body).toEqual({
    message: "Show me the first room",
    thread_id: "search-chat",
    listing_search_context: { message_id: "search-message", page: 2 },
  });
  expect(
    calls
      .filter((call) => call.path === searchPath)
      .every((call) => call.method === "GET"),
  ).toBe(true);
});

it("keeps the current cards after a failed page request and lets the tenant retry", async () => {
  const current = searchThread();
  let failed = true;
  mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/search-chat") return json(current);
    if (path === searchPath)
      return failed
        ? json({ error: { message: "Unable to load this page" } }, 503)
        : json({ items: homes(7, 2), page: 2, page_size: 6, total: 8 });
  });
  renderApp("/tenant/assistant?chat=search-chat");
  await screen.findByRole("link", { name: /Bologna student home 1/ });
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Unable to load this page");
  expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Bologna student home 1/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  failed = false;
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("link", { name: /Bologna student home 7/ });
  expect(
    screen.queryByText("Unable to load this page"),
  ).not.toBeInTheDocument();
});

it("shows an empty search with disabled paging and no duplicate prose", async () => {
  const current = searchThread(0);
  mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/search-chat") return json(current);
  });
  renderApp("/tenant/assistant?chat=search-chat");
  await screen.findByText(/No homes match these preferences/);
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  expect(screen.queryByText(/Text-only duplicate/)).not.toBeInTheDocument();
});

it("returns to a valid page when live results shrink during navigation", async () => {
  const current = searchThread(20);
  let changed = false;
  const { calls } = mockApi(tenant, (path, _method, _body, url) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/search-chat") return json(current);
    if (path === searchPath) {
      const page = Number(url.searchParams.get("page"));
      if (page === 3) changed = true;
      return json({
        items: page === 3 ? [] : homes(page === 2 ? 7 : 1, changed ? 2 : 6),
        page,
        page_size: 6,
        total: changed ? 2 : 20,
      });
    }
  });
  renderApp("/tenant/assistant?chat=search-chat");
  await screen.findByText("Page 1 of 4");
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Page 2 of 4");
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Results changed");
  await userEvent.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findByText("Page 1 of 1");
  expect(
    calls
      .filter((call) => call.path === searchPath)
      .map((call) => call.url.searchParams.get("page")),
  ).toEqual(["2", "3", "1"]);
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

it("keeps explanatory text for mixed search and other assistant work", async () => {
  const current = searchThread();
  current.messages[0].listing_search!.cards_only = false;
  current.messages[0].content =
    "The requested visit could not be prepared. Choose a future time.";
  mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/search-chat") return json(current);
  });
  renderApp("/tenant/assistant?chat=search-chat");
  await screen.findByText(
    "The requested visit could not be prepared. Choose a future time.",
  );
  expect(
    screen.getByRole("link", { name: /Bologna student home 1/ }),
  ).toBeInTheDocument();
});

it("supports cards-only paging and visible-page follow-ups in Blu", async () => {
  const current = searchThread();
  const { calls } = mockApi(tenant, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return json(current);
    if (path === "/assistant/threads/search-chat") return json(current);
    if (path === searchPath)
      return json({ items: homes(7, 2), page: 2, page_size: 6, total: 8 });
  });
  renderApp("/tenant");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const dialog = await screen.findByRole("dialog", { name: "Blu assistant" });
  const input = within(dialog).getByLabelText("Message Blu");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Find rooms in Bologna between €640 and €660");
  await user.click(
    within(dialog).getByRole("button", { name: "Send request to Blu" }),
  );
  await within(dialog).findByRole("link", { name: /Bologna student home 1/ });
  expect(
    within(dialog).queryByText(/Text-only duplicate/),
  ).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Next" }));
  await within(dialog).findByRole("link", { name: /Bologna student home 7/ });
  expect(calls.filter((call) => call.path === "/assistant/chat")).toHaveLength(
    1,
  );
  await user.type(input, "Tell me about the first room");
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
    message: "Tell me about the first room",
    thread_id: "search-chat",
    listing_search_context: { message_id: "search-message", page: 2 },
  });
});
