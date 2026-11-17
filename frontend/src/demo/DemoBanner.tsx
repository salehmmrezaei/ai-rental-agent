import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Button, Feedback } from "../components/ui";
import { useDemo } from "./context";

const roleNames: Record<Role, string> = {
  tenant: "Tenant",
  landlord: "Landlord",
  admin: "Agency",
};

export function DemoRoleChoices() {
  const demo = useDemo();
  const auth = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState<Role>();
  const [error, setError] = useState("");
  if (!demo.enabled) return null;
  return (
    <div className="demo-role-choices">
      <div
        className="demo-role-buttons"
        role="group"
        aria-label="Explore a demo role"
      >
        {demo.roles.map((role) => (
          <Button
            key={role}
            variant={auth.user?.role === role ? "primary" : "secondary"}
            aria-pressed={auth.user?.role === role}
            pending={pending === role}
            disabled={!!pending}
            onClick={async () => {
              setPending(role);
              setError("");
              try {
                await auth.enterDemo(role);
                navigate(`/${role}`);
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "Unable to open this demo role.",
                );
              } finally {
                setPending(undefined);
              }
            }}
          >
            Explore {roleNames[role]}
          </Button>
        ))}
      </div>
      <Feedback error={error} />
    </div>
  );
}

export function DemoBanner() {
  const { enabled } = useDemo();
  if (!enabled) return null;
  return (
    <aside className="demo-banner" aria-label="Fictional portfolio demo">
      <div className="container demo-banner-content">
        <div>
          <strong>Casa · Fictional portfolio demo</strong>
          <p>
            Explore three rental workspaces with synthetic people and homes.
            Shared records are read-only. Blu is a Simulated AI Assistant; no
            live AI service is used.
          </p>
        </div>
        <DemoRoleChoices />
      </div>
    </aside>
  );
}

export function DemoReadOnlyNotice() {
  const { enabled } = useDemo();
  return enabled ? (
    <p className="notice demo-read-only" role="note">
      Read-only demo: explore the records and ask Blu to explain the workflow.
      Changes, account updates, messages and uploads are disabled to preserve
      the shared sample data.
    </p>
  ) : null;
}
