import { expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AssistantThreadDetail } from "../api/assistant";
import type { Listing } from "../api/types";
import { admin, json, mockApi, renderApp } from "./helpers";

const listing: Listing = {
  id: "submitted-listing",
  rental_unit_id: "room-id",
  status: "submitted",
  available_from: "2027-01-01",
  available_until: "2027-07-31",
  review_note: null,
};
function listingThread(): AssistantThreadDetail {
  return {
    id: "agency-chat",
    title: "Listings waiting for review",
    updated_at: "2026-11-02T10:00:00Z",
    messages: [
      {
        id: "reply",
        role: "assistant",
        content: "Here are the listings waiting for review, newest first.",
        listings: [
          {
            id: listing.id,
            title: "Campus Demo Bologna",
            city: "Bologna",
            kind: "room",
            unit_name: "Room Aurora Demo",
            monthly_rent: "650.00",
            available_now: false,
            status: "submitted",
            available_from: listing.available_from,
            available_until: listing.available_until,
          },
          {
            id: "other-listing",
            title: "Florence student home",
            city: "Florence",
            kind: "apartment",
            unit_name: "Entire apartment",
            monthly_rent: "1100.00",
            available_now: false,
            status: "submitted",
            available_from: "2027-02-01",
            available_until: null,
          },
        ],
        actions: [],
        created_at: "2026-11-02T10:00:00Z",
      },
    ],
  };
}

it("opens the exact private listing from saved agency cards and requires confirmation to approve", async () => {
  let currentListing = { ...listing };
  const current = listingThread();
  const { calls } = mockApi(admin, (path, method, body) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([current]);
    if (path === "/assistant/threads/agency-chat") return json(current);
    if (path === "/admin/listings/submitted-listing")
      return json(currentListing);
    if (path === "/units/room-id")
      return json({
        id: "room-id",
        property_id: "property-id",
        name: "Room Aurora Demo",
        monthly_rent: "650.00",
      });
    if (path === "/properties/property-id")
      return json({ id: "property-id", title: "Campus Demo Bologna" });
    if (
      path === "/admin/listings/submitted-listing/status" &&
      method === "PATCH"
    ) {
      currentListing = { ...currentListing, status: body.status };
      return json(currentListing);
    }
  });
  renderApp("/admin/assistant?chat=agency-chat");
  const card = await screen.findByRole("link", { name: /Campus Demo Bologna/ });
  expect(card).toHaveAttribute("href", "/admin/listings/submitted-listing");
  expect(within(card).getByText("Room Aurora Demo")).toBeInTheDocument();
  expect(within(card).getByText("submitted")).toBeInTheDocument();
  expect(card).toHaveTextContent("650");
  expect(card).toHaveTextContent("2027");
  const other = screen.getByRole("link", { name: /Florence student home/ });
  expect(other).toHaveAttribute("href", "/admin/listings/other-listing");
  expect(within(other).getByText(/No end date/)).toBeInTheDocument();
  expect(
    screen.queryByText(/Check availability for your dates/),
  ).not.toBeInTheDocument();

  const user = userEvent.setup();
  await user.click(card);
  await screen.findByRole("heading", { name: "Review listing" });
  await screen.findByRole("heading", { name: "Campus Demo Bologna" });
  expect(
    calls.some((call) => call.path === "/listings/submitted-listing"),
  ).toBe(false);
  expect(calls.every((call) => call.method === "GET")).toBe(true);

  await user.click(screen.getByRole("button", { name: "Approve listing" }));
  const dialog = await screen.findByRole("dialog", { name: "Approve listing" });
  expect(calls.some((call) => call.method === "PATCH")).toBe(false);
  await user.click(
    within(dialog).getByRole("button", { name: "Confirm approval" }),
  );
  await screen.findByRole("button", { name: "Publish listing" });
  expect(calls.filter((call) => call.method === "PATCH")).toHaveLength(1);
  expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({
    status: "approved",
  });
});

it("shows clickable agency listing cards in Blu's new reply", async () => {
  sessionStorage.clear();
  const current = listingThread();
  const { calls } = mockApi(admin, (path) => {
    if (path === "/assistant/status") return json({ available: true });
    if (path === "/assistant/threads") return json([]);
    if (path === "/assistant/chat") return json(current);
    if (path === "/assistant/threads/agency-chat") return json(current);
  });
  renderApp("/admin");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Blu assistant" }));
  const dialog = await screen.findByRole("dialog", { name: "Blu assistant" });
  const input = within(dialog).getByLabelText("Message Blu");
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(
    input,
    "Show me listings waiting for agency review, newest first.",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Send request to Blu" }),
  );
  const card = await within(dialog).findByRole("link", {
    name: /Campus Demo Bologna/,
  });
  expect(card).toHaveAttribute("href", "/admin/listings/submitted-listing");
  expect(
    within(dialog).getByRole("link", { name: /Florence student home/ }),
  ).toHaveAttribute("href", "/admin/listings/other-listing");
  expect(calls.some((call) => call.path.endsWith("/confirm"))).toBe(false);
});

it("handles a listing removed since the assistant reply without opening another record", async () => {
  const { calls } = mockApi(admin, (path) =>
    path === "/admin/listings/missing-listing"
      ? json({ error: { message: "Listing not found" } }, 404)
      : undefined,
  );
  renderApp("/admin/listings/missing-listing");
  await screen.findByText("Listing not found");
  expect(
    screen.getByRole("link", { name: /All listing approvals/ }),
  ).toHaveAttribute("href", "/admin/listings");
  expect(
    screen.queryByRole("button", { name: "Approve listing" }),
  ).not.toBeInTheDocument();
  expect(calls.every((call) => call.method === "GET")).toBe(true);
});
