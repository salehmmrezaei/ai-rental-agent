import { getSession } from "./session";

const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const apiBase = (configured || "/api/v1").replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function queryString(
  values: Record<string, string | number | undefined | null>,
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value !== undefined && value !== null && value !== "")
      params.set(key, String(value));
  return params.toString();
}
interface Options {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  auth?: boolean;
}
export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const session = options.auth === false ? null : getSession();
  const headers = new Headers({ Accept: "application/json" });
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  const isForm = options.body instanceof FormData;
  if (options.body !== undefined && !isForm)
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      method: options.method || "GET",
      headers,
      signal: options.signal,
      cache: "no-store",
      body:
        options.body === undefined
          ? undefined
          : isForm
            ? (options.body as FormData)
            : JSON.stringify(options.body),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(
      0,
      "network_error",
      "Unable to connect. Check your connection and try again.",
    );
  }
  if (!response.ok) {
    let info: {
      error?: {
        code?: string;
        message?: string;
        details?: { location?: string[] }[];
      };
    } = {};
    try {
      info = await response.json();
    } catch {
      /* Proxy failures may return HTML. */
    }
    if (
      response.status === 401 &&
      session &&
      getSession()?.token === session.token
    )
      window.dispatchEvent(
        new CustomEvent("casa:session-expired", { detail: session.token }),
      );
    let message =
      info.error?.message ||
      `Request failed (${response.status}). Please try again.`;
    if (response.status === 422 && info.error?.details?.length) {
      const fields = [
        ...new Set(
          info.error.details
            .map((d) =>
              d.location
                ?.filter((p) => !["body", "query"].includes(p))
                .join(" ")
                .replaceAll("_", " "),
            )
            .filter(Boolean),
        ),
      ];
      if (fields.length) message = `Please check: ${fields.join(", ")}.`;
    }
    throw new ApiError(
      response.status,
      info.error?.code || "request_failed",
      message,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function imageUrl(path: string) {
  // Only serve backend image routes; never attach a token to a supplied arbitrary URL.
  if (!/^\/api\/v1\/images\/[a-f0-9-]+$/i.test(path)) return "";
  return apiBase + path.slice("/api/v1".length);
}
export async function imageBlob(path: string, signal: AbortSignal) {
  const url = imageUrl(path);
  if (!url) throw new Error("Invalid image path");
  const headers = new Headers();
  const session = getSession();
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  const response = await fetch(url, { headers, signal, cache: "no-store" });
  if (!response.ok) throw new Error("Image unavailable");
  return response.blob();
}
