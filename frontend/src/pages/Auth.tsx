import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Building2, KeyRound } from "lucide-react";
import { api } from "../api/client";
import type { User } from "../api/types";
import { dashboardPath, useAuth } from "../auth/AuthProvider";
import {
  Button,
  Field,
  Feedback,
  Select,
  formData,
  text,
} from "../components/ui";
import { useAction } from "../hooks/useAction";
export function safeNext(value: string | null, role: User["role"]) {
  if (
    value?.startsWith("/") &&
    !value.startsWith("//") &&
    !value.includes("\\") &&
    !/^\/(login|register)(?:[/?#]|$)/.test(value)
  )
    return value;
  return dashboardPath(role);
}
export function AuthPage({ register = false }: { register?: boolean }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const action = useAction();
  const [showPassword, setShowPassword] = useState(false);
  if (auth.user)
    return (
      <Navigate to={safeNext(params.get("next"), auth.user.role)} replace />
    );
  return (
    <div className="container auth-page">
      <aside className="auth-story">
        <p className="eyebrow">A place to live. Room to grow.</p>
        <h1>
          {register ? (
            <>
              Make yourself
              <br />
              <em>at home.</em>
            </>
          ) : (
            <>
              Welcome back
              <br />
              to <em>your next chapter.</em>
            </>
          )}
        </h1>
        <div className="auth-architecture">
          <Building2 size={140} strokeWidth={0.65} />
          <KeyRound size={50} strokeWidth={1} />
        </div>
        <p>
          One account for your search, visits, rental applications and
          conversations with the agency.
        </p>
      </aside>
      <section className="auth-form-panel">
        <p className="eyebrow">{register ? "Get started" : "Your account"}</p>
        <h1>{register ? "A new beginning." : "Good to see you."}</h1>
        <p>
          {register
            ? "Create an account to find or manage a home."
            : "Sign in to pick up where you left off."}
        </p>
        <Feedback
          error={action.error}
          success={
            params.get("notice") === "updated"
              ? "Account updated. Sign in with your current credentials."
              : null
          }
        />
        <form
          onSubmit={(event) => {
            const data = formData(event);
            void action.run(async () => {
              const email = text(data, "email");
              const password = String(data.get("password") || "");
              if (register)
                await api<User>("/auth/register", {
                  method: "POST",
                  auth: false,
                  body: {
                    full_name: text(data, "full_name"),
                    email,
                    password,
                    role: text(data, "role"),
                  },
                });
              const user = await auth.signIn(email, password);
              navigate(safeNext(params.get("next"), user.role), {
                replace: true,
              });
            });
          }}
          className="form-stack"
        >
          {register && (
            <>
              <Field
                label="Full name"
                name="full_name"
                required
                maxLength={150}
                autoComplete="name"
              />
              <Select
                label="I’m here to…"
                name="role"
                defaultValue={
                  params.get("role") === "landlord" ? "landlord" : "tenant"
                }
              >
                <option value="tenant">Find a home</option>
                <option value="landlord">List and manage my properties</option>
              </Select>
            </>
          )}
          <Field
            label="Email address"
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
          />
          <Field
            label="Password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete={register ? "new-password" : "current-password"}
            required
            minLength={register ? 12 : 1}
            maxLength={128}
            hint={register ? "At least 12 characters." : undefined}
          />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
            />
            Show password
          </label>
          <Button type="submit" pending={action.pending}>
            {register ? "Create account" : "Sign in"}
            <ArrowRight size={17} />
          </Button>
        </form>
        <p className="auth-switch">
          {register ? "Already have an account?" : "New around here?"}{" "}
          <Link
            to={`${register ? "/login" : "/register"}${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`}
          >
            {register ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </section>
    </div>
  );
}
