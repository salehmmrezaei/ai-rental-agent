import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "../api/client";
import {
  getSession,
  readSession,
  sessionStorageKey,
  setSession,
} from "../api/session";
import type { TokenResponse, User } from "../api/types";

interface AuthState {
  user: User | null;
  status: "loading" | "ready" | "error";
  error: string | null;
  epoch: number;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
  clear: () => void;
  refresh: (silent?: boolean) => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);
  const generation = useRef(0);
  const clear = useCallback(() => {
    generation.current++;
    setSession(null);
    setUser(null);
    setStatus("ready");
    setError(null);
    setEpoch((e) => e + 1);
  }, []);
  const refresh = useCallback(
    async (silent = false) => {
      const run = ++generation.current;
      if (!silent) setStatus("loading");
      setError(null);
      if (!getSession()) {
        setUser(null);
        setStatus("ready");
        return;
      }
      try {
        const value = await api<User>("/users/me");
        if (run === generation.current) {
          setUser(value);
          setStatus("ready");
          setEpoch((e) => e + 1);
        }
      } catch (e) {
        if (run !== generation.current) return;
        if (e instanceof ApiError && e.status === 401) clear();
        else {
          setUser(null);
          setError(
            e instanceof Error ? e.message : "Unable to verify your session.",
          );
          setStatus("error");
        }
      }
    },
    [clear],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    const expired = (event: Event) => {
      if ((event as CustomEvent).detail === getSession()?.token) clear();
    };
    const changed = (event: StorageEvent) => {
      if (event.key === sessionStorageKey) {
        setSession(readSession());
        void refresh();
      }
    };
    window.addEventListener("casa:session-expired", expired);
    window.addEventListener("storage", changed);
    return () => {
      window.removeEventListener("casa:session-expired", expired);
      window.removeEventListener("storage", changed);
    };
  }, [clear, refresh]);
  useEffect(() => {
    const value = getSession();
    if (!value || !user) return;
    const timer = window.setTimeout(
      clear,
      Math.max(0, value.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [user, clear]);
  async function signIn(email: string, password: string) {
    const run = ++generation.current;
    const result = await api<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    if (run !== generation.current)
      throw new Error("Sign-in interrupted. Please try again.");
    setSession({
      token: result.access_token,
      expiresAt: Date.now() + result.expires_in * 1000,
    });
    setUser(result.user);
    setStatus("ready");
    setError(null);
    setEpoch((e) => e + 1);
    return result.user;
  }
  async function signOut() {
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } finally {
      clear();
    }
  }
  return (
    <AuthContext.Provider
      value={{ user, status, error, epoch, signIn, signOut, clear, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is required");
  return context;
}
export function dashboardPath(role: User["role"]) {
  return `/${role}`;
}
