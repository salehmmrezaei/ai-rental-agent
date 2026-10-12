import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth, dashboardPath } from "./AuthProvider";
import type { Role } from "../api/types";
import { Button, Feedback, Loading } from "../components/ui";
export function AuthGate({ roles }: { roles: Role[] }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading")
    return <Loading label="Checking your session…" />;
  if (auth.status === "error")
    return (
      <div className="container panel">
        <Feedback error={auth.error} />
        <Button onClick={() => void auth.refresh()}>Retry session check</Button>
        <Button variant="secondary" onClick={auth.clear}>
          Sign in again
        </Button>
      </div>
    );
  if (!auth.user)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  if (!roles.includes(auth.user.role))
    return <Navigate to={dashboardPath(auth.user.role)} replace />;
  return <Outlet />;
}
export function DashboardRedirect() {
  const { user, status } = useAuth();
  if (status === "loading") return <Loading />;
  return <Navigate to={user ? dashboardPath(user.role) : "/login"} replace />;
}
