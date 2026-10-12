import { expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  mockApi,
  renderApp,
  tenant,
  landlord,
  admin,
  listing,
  json,
  page,
} from "./helpers";
const application = {
  id: "request-id",
  property_title: listing.title,
  unit_name: "Room A",
  property_id: "property-id",
  tenant_id: tenant.id,
  rental_unit_id: "unit-id",
  start_date: "2027-01-01",
  end_date: "2027-03-01",
  status: "submitted",
  note: null,
  review_note: null,
};
it("serializes search preferences into backend filters", async () => {
  const { calls } = mockApi(undefined, (path) =>
    path === "/listings" ? json(page([listing])) : undefined,
  );
  renderApp("/listings");
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: listing.title });
  await user.selectOptions(screen.getByLabelText("Where"), "Bologna");
  await user.selectOptions(screen.getByLabelText("Home type"), "room");
  await user.type(screen.getByLabelText("Max. rent (€ / month)"), "800");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  await screen.findByRole("heading", { name: "Homes in Bologna" });
  await waitFor(() =>
    expect(
      calls.some(
        (c) =>
          c.url.searchParams.get("max_price") === "800" &&
          c.url.searchParams.get("property_type") === "room",
      ),
    ).toBe(true),
  );
});
it("validates paired search dates", async () => {
  mockApi();
  renderApp("/listings");
  await screen.findByRole("heading", { name: "Find your next home" });
  await userEvent.type(screen.getByLabelText("Move-in"), "2027-01-01");
  await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await screen.findByText(
    "Choose both rental dates, with move-out after move-in.",
  );
});
it("shows backend failure and retries", async () => {
  let failed = true;
  mockApi(undefined, (path) =>
    path === "/listings"
      ? failed
        ? json({ error: { message: "Unavailable" } }, 503)
        : json(page([]))
      : undefined,
  );
  renderApp("/listings");
  await screen.findByText("Unavailable");
  failed = false;
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("No homes match just yet");
});
it("checks full-stay availability before persisting an application", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/listings/listing-id"
      ? json(listing)
      : path.endsWith("/availability")
        ? json({ available: true, reason: "available" })
        : path === "/applications"
          ? json(page([application]))
          : undefined,
  );
  renderApp("/listings/listing-id");
  await screen.findByRole("heading", { name: listing.title });
  const user = userEvent.setup();
  expect(
    screen.getByRole("button", { name: "Apply for this home" }),
  ).toBeDisabled();
  await user.type(screen.getByLabelText("Move-in"), "2027-01-01");
  await user.type(screen.getByLabelText("Move-out"), "2027-03-01");
  await user.click(screen.getByRole("button", { name: "Check dates" }));
  await screen.findByText("Available for these dates.");
  await user.click(screen.getByRole("button", { name: "Apply for this home" }));
  await user.click(screen.getByRole("button", { name: "Submit application" }));
  await screen.findByRole("heading", { name: "Your applications" });
  expect(
    calls.find((c) => c.path === "/applications" && c.method === "POST")?.body,
  ).toEqual({
    listing_id: listing.id,
    start_date: "2027-01-01",
    end_date: "2027-03-01",
  });
});
it("withdraws only the selected application after confirmation", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/applications"
      ? json(page([application]))
      : path.endsWith("/withdraw")
        ? json({ ...application, status: "withdrawn" })
        : undefined,
  );
  renderApp("/tenant/applications");
  await screen.findByText(listing.title);
  await userEvent.click(
    screen.getByRole("button", { name: "Withdraw application" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm withdrawal" }),
  );
  await waitFor(() =>
    expect(
      calls.some(
        (c) =>
          c.path === "/applications/request-id/withdraw" && c.method === "POST",
      ),
    ).toBe(true),
  );
});
it("uses the transactional agency approval endpoint", async () => {
  const { calls } = mockApi(admin, (path) =>
    path === "/admin/applications"
      ? json(page([application]))
      : path.endsWith("/approve")
        ? json({ id: "contract-id" })
        : undefined,
  );
  renderApp("/admin/applications");
  await screen.findByText(listing.title);
  await userEvent.click(
    screen.getByRole("button", { name: "Approve & create contract" }),
  );
  await userEvent.type(
    screen.getByLabelText("Monthly rent override (€, optional)"),
    "675",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm approval" }),
  );
  await waitFor(() =>
    expect(calls.find((c) => c.path.endsWith("/approve"))?.body).toEqual({
      monthly_rent: "675",
    }),
  );
});
it("keeps an approval conflict visible without pretending success", async () => {
  mockApi(admin, (path) =>
    path === "/admin/applications"
      ? json(page([application]))
      : path.endsWith("/approve")
        ? json({ error: { message: "Requested dates are not available" } }, 409)
        : undefined,
  );
  renderApp("/admin/applications");
  await screen.findByText(listing.title);
  await userEvent.click(
    screen.getByRole("button", { name: "Approve & create contract" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm approval" }),
  );
  await within(screen.getByRole("dialog")).findByText(
    "Requested dates are not available",
  );
  expect(
    screen.queryByText("Application approved and contract created."),
  ).not.toBeInTheDocument();
});
it("removes an unpublished saved listing by saved-record ID", async () => {
  const { calls } = mockApi(tenant, (path) =>
    path === "/saved-listings"
      ? json(page([{ id: "saved-id", listing_id: listing.id, listing: null }]))
      : path === "/saved-listings/saved-id"
        ? json(null, 204)
        : undefined,
  );
  renderApp("/tenant/saved");
  await screen.findByText("This listing is currently unavailable");
  await userEvent.click(
    screen.getByRole("button", { name: "Remove saved home" }),
  );
  await waitFor(() =>
    expect(
      calls.some(
        (c) => c.path === "/saved-listings/saved-id" && c.method === "DELETE",
      ),
    ).toBe(true),
  );
});
it("persists a landlord property without client-supplied ownership", async () => {
  const { calls } = mockApi(landlord, (path, method) =>
    path === "/properties" && method === "POST"
      ? json({ id: "property-id" }, 201)
      : path === "/properties/property-id"
        ? json({
            id: "property-id",
            title: "New synthetic home",
            address: "Synthetic Street",
            city: "Rome",
            postal_code: "00100",
            amenities: [],
            units: [],
            images: [],
          })
        : undefined,
  );
  renderApp("/landlord/properties/new");
  const user = userEvent.setup();
  await screen.findByLabelText("Property title");
  for (const [label, value] of [
    ["Property title", "New synthetic home"],
    ["Description", "Synthetic development rental"],
    ["City", "Rome"],
    ["Postal code", "00100"],
    ["Address", "Synthetic Street"],
  ])
    await user.type(screen.getByLabelText(label), value);
  await user.click(screen.getByRole("button", { name: "Create property" }));
  await screen.findByRole("heading", { name: "New synthetic home" });
  expect(
    calls.find((c) => c.method === "POST")?.body.landlord_id,
  ).toBeUndefined();
});
it("freezes reviewed property content", async () => {
  mockApi(landlord, (path) =>
    path === "/properties/property-id"
      ? json({
          id: "property-id",
          title: listing.title,
          address: listing.address,
          description: listing.description,
          city: "Bologna",
          postal_code: "40121",
          amenities: [],
          images: [],
          units: [{ id: "unit-id", listing: { status: "submitted" } }],
        })
      : undefined,
  );
  renderApp("/landlord/properties/property-id/edit");
  await screen.findByLabelText("Property title");
  expect(screen.getByRole("button", { name: "Save property" })).toBeDisabled();
  expect(screen.getByLabelText("Property title")).toBeDisabled();
});
it("persists replies with server-derived authorship and marks incoming messages read", async () => {
  const conversation = {
    id: "conversation-id",
    subject: "Synthetic support",
    unread_count: 1,
    updated_at: new Date().toISOString(),
  };
  const { calls } = mockApi(tenant, (path) =>
    path === "/conversations"
      ? json(page([conversation]))
      : path === "/conversations/conversation-id"
        ? json(conversation)
        : path.endsWith("/messages")
          ? json(
              page([
                {
                  id: "message-id",
                  sender_type: "agency",
                  body: "Welcome home",
                  created_at: new Date().toISOString(),
                  read_at: null,
                },
              ]),
            )
          : path.endsWith("/read")
            ? json({ updated: 1 })
            : undefined,
  );
  renderApp("/tenant/messages?conversation=conversation-id");
  await screen.findByText("Welcome home");
  await userEvent.type(screen.getByLabelText("Your reply"), "Thank you");
  await userEvent.click(screen.getByRole("button", { name: "Send reply" }));
  await waitFor(() =>
    expect(
      calls.find((c) => c.path.endsWith("/messages") && c.method === "POST")
        ?.body,
    ).toEqual({ body: "Thank you" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Mark 1 as read" }));
  await waitFor(() =>
    expect(
      calls.some((c) => c.path.endsWith("/read") && c.method === "POST"),
    ).toBe(true),
  );
});

it("user management persists activation without granting client-side roles", async () => {
  const { calls } = mockApi(admin, (path, method) =>
    path === "/admin/users"
      ? json(page([tenant]))
      : path === "/admin/users/tenant-id" && method === "PATCH"
        ? json({ ...tenant, is_active: false })
        : undefined,
  );
  renderApp("/admin/users");
  await screen.findByRole("button", { name: `Edit ${tenant.full_name}` });
  await userEvent.click(
    screen.getByRole("button", { name: `Edit ${tenant.full_name}` }),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("Account access"),
    "false",
  );
  await userEvent.click(screen.getByRole("button", { name: "Save user" }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      full_name: tenant.full_name,
      email: tenant.email,
      is_active: false,
    }),
  );
});
it("contract termination submits the effective date and leaves original dates intact", async () => {
  const contract = {
    id: "contract-id",
    property_id: "property-id",
    property_title: listing.title,
    unit_name: "Room A",
    status: "active",
    start_date: "2026-01-01",
    end_date: "2030-01-01",
    effective_end_date: "2030-01-01",
    monthly_rent: "675",
    terminated_on: null,
  };
  const { calls } = mockApi(admin, (path) =>
    path === "/contracts"
      ? json(page([contract]))
      : path === "/admin/contracts/contract-id"
        ? json(contract)
        : undefined,
  );
  renderApp("/admin/contracts");
  await screen.findByText(listing.title);
  await userEvent.click(screen.getByRole("button", { name: "Terminate" }));
  await userEvent.clear(screen.getByLabelText("Effective end date"));
  await userEvent.type(
    screen.getByLabelText("Effective end date"),
    "2027-01-01",
  );
  await userEvent.click(screen.getByRole("button", { name: "Confirm change" }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      status: "terminated",
      terminated_on: "2027-01-01",
    }),
  );
});
it("upload forms send the real file and omit unselected room association", async () => {
  const property = {
    id: "property-id",
    title: listing.title,
    city: "Bologna",
    address: listing.address,
    postal_code: "40121",
    description: listing.description,
    amenities: [],
    images: [],
    units: [],
  };
  const { calls } = mockApi(landlord, (path) =>
    path === "/properties/property-id"
      ? json(property)
      : path.endsWith("/images")
        ? json({ id: "image-id" }, 201)
        : undefined,
  );
  renderApp("/landlord/properties/property-id");
  await screen.findByText(listing.title);
  await userEvent.click(screen.getByRole("button", { name: /Pictures/ }));
  await userEvent.click(screen.getByRole("button", { name: "Upload photo" }));
  await userEvent.upload(
    screen.getByLabelText("Photo file"),
    new File(["synthetic image bytes"], "synthetic.png", { type: "image/png" }),
  );
  await userEvent.type(
    screen.getByLabelText("Photo description"),
    "Synthetic photo",
  );
  // user-event exposes a synthetic FileList; jsdom's form serializer does not
  // see that patched list. Preserve the chosen file in this environment.
  // jsdom's native required-file validator also uses its backing FileList.
  screen.getByLabelText("Photo file").closest("form")!.noValidate = true;
  const BrowserFormData = window.FormData;
  vi.stubGlobal(
    "FormData",
    class extends BrowserFormData {
      constructor(form?: HTMLFormElement) {
        super(form);
        for (const input of form?.querySelectorAll<HTMLInputElement>(
          'input[type="file"]',
        ) || []) {
          if (input.files?.[0]) this.set(input.name, input.files[0]);
        }
      }
    },
  );
  await userEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Upload photo",
    }),
  );
  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST")).toBe(true),
  );
  const body = calls.find((c) => c.method === "POST")!.body as FormData;
  expect(body.get("file")).toBeInstanceOf(File);
  expect(body.has("rental_unit_id")).toBe(false);
});
it("directory pagination in a form does not accidentally submit that form", async () => {
  const { UserPicker } = await import("../components/UserPicker");
  const { AuthProvider } = await import("../auth/AuthProvider");
  const { render } = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  const { vi } = await import("vitest");
  const submitted = vi.fn();
  mockApi(admin, (path, _method, _body, url) =>
    path === "/admin/users"
      ? json({
          ...page([landlord], 150),
          page: Number(url.searchParams.get("page")),
          page_size: 100,
        })
      : undefined,
  );
  render(
    <MemoryRouter>
      <AuthProvider>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submitted();
          }}
        >
          <UserPicker
            role="landlord"
            name="landlord_id"
            label="Owner"
            initial={landlord}
          />
        </form>
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByLabelText("Owner");
  await userEvent.click(screen.getByRole("button", { name: /Next/ }));
  await screen.findByText("Page 2 of 2");
  expect(submitted).not.toHaveBeenCalled();
});
