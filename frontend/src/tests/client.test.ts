import { expect, it, vi } from "vitest";
import { api, ApiError, imageUrl, queryString } from "../api/client";
import { readSession, setSession } from "../api/session";
import { json } from "./helpers";
it("sends bearer tokens and JSON and handles 204", async () => {
  setSession({ token: "synthetic-token", expiresAt: Date.now() + 60000 });
  const fetch = vi.fn().mockResolvedValue(json(null, 204));
  vi.stubGlobal("fetch", fetch);
  await expect(
    api("/applications/id/withdraw", { method: "POST", body: {} }),
  ).resolves.toBeUndefined();
  const options = fetch.mock.calls[0][1];
  expect(options.headers.get("Authorization")).toBe("Bearer synthetic-token");
  expect(options.body).toBe("{}");
});
it("lets the browser set multipart boundaries", async () => {
  const fetch = vi.fn().mockResolvedValue(json({ id: "image" }));
  vi.stubGlobal("fetch", fetch);
  const body = new FormData();
  body.set("alt_text", "Synthetic photo");
  await api("/properties/id/images", { method: "POST", body });
  expect(fetch.mock.calls[0][1].body).toBe(body);
  expect(fetch.mock.calls[0][1].headers.has("Content-Type")).toBe(false);
});
it("returns readable validation errors without input values", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      json(
        {
          error: {
            code: "validation_error",
            details: [{ location: ["body", "start_date"] }],
          },
        },
        422,
      ),
    ),
  );
  await expect(api("/applications")).rejects.toThrow(
    "Please check: start date.",
  );
});
it("reports proxy and network failures", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })),
  );
  await expect(api("/listings")).rejects.toBeInstanceOf(ApiError);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
  );
  await expect(api("/listings")).rejects.toThrow("Unable to connect");
});
it("signals token invalidation on authenticated 401 only", async () => {
  const listener = vi.fn();
  window.addEventListener("casa:session-expired", listener);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(json({ error: { message: "Unauthorized" } }, 401)),
  );
  setSession({ token: "synthetic-token", expiresAt: Date.now() + 60000 });
  await api("/users/me").catch(() => {});
  expect(listener).toHaveBeenCalledTimes(1);
  await api("/auth/login", { method: "POST", auth: false }).catch(() => {});
  expect(listener).toHaveBeenCalledTimes(1);
  window.removeEventListener("casa:session-expired", listener);
});
it("rejects malformed or expired storage and arbitrary image URLs", () => {
  localStorage.setItem("casa.session", "{invalid");
  expect(readSession()).toBeNull();
  localStorage.setItem(
    "casa.session",
    JSON.stringify({ token: "old", expiresAt: 1 }),
  );
  expect(readSession()).toBeNull();
  expect(imageUrl("https://example.com/image")).toBe("");
  expect(imageUrl("/api/v1/images/abcdef-123")).toBe(
    "/api/v1/images/abcdef-123",
  );
  expect(queryString({ city: "Rome", empty: "", none: null, page: 2 })).toBe(
    "city=Rome&page=2",
  );
});
