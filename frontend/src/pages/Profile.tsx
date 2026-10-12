import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { useAction } from "../hooks/useAction";
import {
  Button,
  Feedback,
  Field,
  PageTitle,
  formData,
  text,
} from "../components/ui";
export function ProfilePage() {
  const auth = useAuth();
  const user = auth.user!;
  const action = useAction();
  const password = useAction();
  const navigate = useNavigate();
  return (
    <>
      <PageTitle
        title="Your profile"
        description="Keep your details up to date and your account secure."
      />
      <div className="profile-grid">
        <section className="panel">
          <h2>Personal details</h2>
          <Feedback error={action.error} success={action.success} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                const body: Record<string, string> = {
                  full_name: text(data, "full_name"),
                };
                const changedEmail =
                  text(data, "email").toLowerCase() !== user.email;
                if (changedEmail) {
                  body.email = text(data, "email");
                  body.current_password = String(
                    data.get("current_password") || "",
                  );
                  if (!body.current_password)
                    throw new Error(
                      "Enter your current password to change your email.",
                    );
                }
                await api("/users/me", { method: "PATCH", body });
                if (changedEmail) {
                  auth.clear();
                  navigate("/login?notice=updated");
                } else await auth.refresh(true);
              }, "Profile saved.");
            }}
          >
            <Field
              label="Full name"
              name="full_name"
              required
              maxLength={150}
              defaultValue={user.full_name}
              autoComplete="name"
            />
            <Field
              label="Email address"
              name="email"
              type="email"
              required
              maxLength={254}
              defaultValue={user.email}
              autoComplete="email"
            />
            <Field
              label="Current password (for email changes)"
              name="current_password"
              type="password"
              autoComplete="current-password"
              hint="Changing your email signs you out on all devices."
            />
            <Button type="submit" pending={action.pending}>
              Save details
            </Button>
          </form>
        </section>
        <section className="panel">
          <h2>Change password</h2>
          <Feedback error={password.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void password.run(async () => {
                const newPassword = String(data.get("new_password") || "");
                if (newPassword !== String(data.get("confirmation") || ""))
                  throw new Error("The new passwords do not match.");
                await api("/users/me/password", {
                  method: "PUT",
                  body: {
                    current_password: String(
                      data.get("current_password") || "",
                    ),
                    new_password: newPassword,
                  },
                });
                auth.clear();
                navigate("/login?notice=updated");
              });
            }}
          >
            <Field
              label="Current password"
              name="current_password"
              type="password"
              required
              autoComplete="current-password"
            />
            <Field
              label="New password"
              name="new_password"
              type="password"
              required
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              hint="Use at least 12 characters."
            />
            <Field
              label="Confirm new password"
              name="confirmation"
              type="password"
              required
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
            />
            <Button type="submit" pending={password.pending}>
              Update password
            </Button>
            <p className="muted">You’ll sign in again after this change.</p>
          </form>
        </section>
      </div>
    </>
  );
}
