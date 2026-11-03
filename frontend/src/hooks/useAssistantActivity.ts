import { useSyncExternalStore } from "react";

const requests = new Set<symbol>();
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Track a submitted assistant request until it settles or is aborted. */
export function beginAssistantRequest(signal: AbortSignal) {
  if (signal.aborted) return () => {};
  const request = Symbol();
  const finish = () => {
    signal.removeEventListener("abort", finish);
    if (requests.delete(request)) notify();
  };
  requests.add(request);
  signal.addEventListener("abort", finish, { once: true });
  notify();
  return finish;
}

export function useAssistantBusy() {
  return useSyncExternalStore(
    subscribe,
    () => requests.size > 0,
    () => false,
  );
}
