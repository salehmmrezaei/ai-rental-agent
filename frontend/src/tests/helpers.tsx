import { vi } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import { setSession } from "../api/session";
import type { User, PublicListing } from "../api/types";
import { today } from "../components/ui";
export const tenant: User = {
  id: "tenant-id",
  full_name: "Synthetic Tenant",
  email: "synthetic.tenant@example.com",
  role: "tenant",
  is_active: true,
  created_at: today(),
  updated_at: today(),
};
export const landlord: User = {
  ...tenant,
  id: "owner-id",
  full_name: "Synthetic Owner",
  role: "landlord",
};
export const admin: User = {
  ...tenant,
  id: "agent-id",
  full_name: "Synthetic Agent",
  role: "admin",
};
export const listing: PublicListing = {
  id: "listing-id",
  property_id: "property-id",
  rental_unit_id: "unit-id",
  title: "Synthetic Bologna home",
  description: "A quiet place to settle in.",
  city: "Bologna",
  address: "Synthetic Via Esempio 10",
  postal_code: "40121",
  is_synthetic: true,
  kind: "room",
  unit_name: "Room A",
  monthly_rent: "650.00",
  deposit: "500.00",
  bedrooms: 1,
  area_sqm: "18",
  amenities: ["wifi"],
  images: [],
  available_from: today(),
  available_until: "2030-01-01",
  available_now: true,
};
export function page<T>(items: T[], total = items.length) {
  return { items, total, page: 1, page_size: 20 };
}
export function json(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
export type Handler = (
  path: string,
  method: string,
  body: any,
  url: URL,
) => Response | Promise<Response> | undefined;
export function mockApi(user?: User, handler?: Handler) {
  const calls: {
    path: string;
    method: string;
    body: any;
    headers: Headers;
    url: URL;
  }[] = [];
  const fetchMock = vi.fn(
    async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const path = url.pathname.replace("/api/v1", "");
      const method = init?.method || "GET";
      const body =
        typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      calls.push({
        path,
        method,
        body,
        headers: new Headers(init?.headers),
        url,
      });
      const custom = await handler?.(path, method, body, url);
      if (custom) return custom;
      if (path === "/users/me")
        return user
          ? json(user)
          : json({ error: { message: "Not authenticated" } }, 401);
      if (path === "/dashboard/statistics")
        return json({
          role: user?.role,
          counts: { pending_applications: 0 },
          occupancy: null,
        });
      if (path === "/listings") return json(page([]));
      return json(
        { error: { message: `Unexpected test request: ${method} ${path}` } },
        404,
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  if (user)
    setSession({ token: "synthetic-token", expiresAt: Date.now() + 3600000 });
  return { calls, fetchMock };
}
export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
