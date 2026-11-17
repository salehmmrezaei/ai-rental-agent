const KEY = "casa.session";
const DEMO_KEY = "casa.demo.session";
export interface SessionRecord {
  token: string;
  expiresAt: number;
  demo?: boolean;
  demoId?: string;
}
export function readSession(): SessionRecord | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(DEMO_KEY) || "null");
    if (
      value?.demo === true &&
      typeof value.token === "string" &&
      value.token &&
      typeof value.expiresAt === "number" &&
      value.expiresAt > Date.now()
    )
      return value as SessionRecord;
    sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* Demo access also works in memory when session storage is unavailable. */
  }
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
    if (value?.demo) sessionStorage.setItem(DEMO_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* Demo sessions can remain in memory for this page. */
  }
  try {
    if (value && !value.demo) localStorage.setItem(KEY, JSON.stringify(value));
    else localStorage.removeItem(KEY);
  } catch {
    /* Private browsing can deny persistent storage. */
  }
}
export const sessionStorageKey = KEY;
