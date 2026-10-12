import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

export function useResource<T>(path: string | null) {
  const { epoch, user } = useAuth();
  const key = `${user?.id || "public"}:${epoch}:${path}`;
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{
    key: string;
    data?: T;
    error?: string;
    loading: boolean;
  }>({ key: "", loading: !!path });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState({ key, loading: true });
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ key, data, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            key,
            error:
              error instanceof Error ? error.message : "Unable to load data.",
            loading: false,
          });
      });
    return () => controller.abort();
  }, [path, key, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return {
    data: state.key === key ? state.data : undefined,
    error: state.key === key ? state.error : undefined,
    loading: !!path && (state.key !== key || state.loading),
    reload,
  };
}
