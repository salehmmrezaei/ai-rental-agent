const KEY = "casa.session";
export interface SessionRecord {
  token: string;
  expiresAt: number;
}
export function readSession(): SessionRecord | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) || "null");
    if (
      value &&
      typeof value === "object" &&
      "token" in value &&
      typeof value.token === "string" &&
      value.token &&
      "expiresAt" in value &&
      typeof value.expiresAt === "number" &&
      value.expiresAt > Date.now()
    ) {
      return value as SessionRecord;
    }
    localStorage.removeItem(KEY);
  } catch {
    /* Storage can be unavailable; in-memory auth still works. */
  }
  return null;
}
let current: SessionRecord | null = readSession();
export function getSession() {
  return current;
}
export function setSession(value: SessionRecord | null) {
  current = value;
  try {
    if (value) localStorage.setItem(KEY, JSON.stringify(value));
    else localStorage.removeItem(KEY);
  } catch {
    /* Private browsing can deny persistent storage. */
  }
}
export const sessionStorageKey = KEY;
