import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import { getSession } from "../api/session";
import { useAuth } from "../auth/AuthProvider";
import { DemoContext, normal } from "./context";
import type { DemoStatus } from "./context";

export function DemoProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<DemoStatus>();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const { clear } = useAuth();
  useEffect(() => {
    const controller = new AbortController();
    api<DemoStatus>("/demo/status", { auth: false, signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        const session = getSession();
        if (session && Boolean(session.demo) !== value.enabled) clear();
        setStatus(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [attempt, clear]);
  if (failed)
    return (
      <div className="container demo-loading" role="status">
        <p>Unable to load Casa’s settings. Please try again.</p>
        <button
          className="btn btn-primary"
          onClick={() => {
            setFailed(false);
            setAttempt((n) => n + 1);
          }}
        >
          Retry loading Casa
        </button>
      </div>
    );
  return (
    <DemoContext.Provider value={status || { ...normal, loading: true }}>
      {children}
    </DemoContext.Provider>
  );
}
