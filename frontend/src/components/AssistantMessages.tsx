import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Bot, Check } from "lucide-react";
import type { AssistantAction, AssistantMessage } from "../api/assistant";
import { Button, day, money, time } from "./ui";

const actionDestinations: Record<string, [string, string]> = {
  save_listing: ["/tenant/saved", "View saved homes"],
  apply: ["/tenant/applications", "View applications"],
  withdraw_application: ["/tenant/applications", "View applications"],
  request_visit: ["/tenant/visits", "View visits"],
  cancel_visit: ["/tenant/visits", "View visits"],
  contact_agency: ["/tenant/messages", "View agency messages"],
  send_message: ["/tenant/messages", "View agency messages"],
};
const fieldLabels: Record<string, string> = {
  start_date: "Move-in",
  end_date: "Move-out",
  requested_at: "Preferred visit time",
  note: "Your note",
  subject: "Subject",
  initial_message: "Message",
  body: "Message",
  quoted_monthly_rent: "Quoted monthly rent",
};

export function AssistantActionCard({
  action,
  busy,
  resolve,
}: {
  action: AssistantAction;
  busy: boolean;
  resolve: (action: AssistantAction, confirm: boolean) => void;
}) {
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 10000);
    return () => window.clearInterval(timer);
  }, []);
  const expired = new Date(action.expires_at).getTime() <= clock;
  const destination = actionDestinations[action.kind];
  return (
    <section className="assistant-action" aria-label="Review proposed action">
      <p className="eyebrow">
        {action.status === "confirmed"
          ? "Action completed"
          : action.status === "cancelled"
            ? "Action dismissed"
            : "Review before confirming"}
      </p>
      <h3>{action.summary}</h3>
      <dl>
        {Object.entries(action.payload)
          .filter(([key, value]) => fieldLabels[key] && value)
          .map(([key, value]) => (
            <div key={key}>
              <dt>{fieldLabels[key]}</dt>
              <dd>
                {key.endsWith("_date")
                  ? day(value)
                  : key === "requested_at"
                    ? `${time(value)} (Europe/Rome)`
                    : key === "quoted_monthly_rent" && value
                      ? `${money(value)} / month`
                      : value}
              </dd>
            </div>
          ))}
      </dl>
      {action.status === "pending" ? (
        <>
          <p className="muted">
            {expired
              ? "This proposal expired. Ask for a new one."
              : `Expires ${time(action.expires_at)}. Confirming performs this action.`}
          </p>
          <div className="assistant-action-buttons">
            <Button
              disabled={busy || expired}
              onClick={() => resolve(action, true)}
            >
              <Check size={16} />
              Confirm action
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => resolve(action, false)}
            >
              Dismiss
            </Button>
          </div>
        </>
      ) : action.status === "confirmed" && destination ? (
        <Link className="text-link" to={destination[0]}>
          {destination[1]}
          <ArrowUpRight size={15} />
        </Link>
      ) : null}
    </section>
  );
}

export function AssistantMessageView({
  message,
  busy,
  onAction,
  assistantName = "Casa assistant",
}: {
  message: AssistantMessage;
  busy: boolean;
  onAction: (action: AssistantAction, confirm: boolean) => void;
  assistantName?: string;
}) {
  return (
    <article
      className={`assistant-message ${message.role === "user" ? "own" : ""}`}
    >
      <p className="assistant-speaker">
        {message.role === "user" ? (
          "You"
        ) : (
          <>
            <Bot size={16} />
            {assistantName}
          </>
        )}
      </p>
      <p className="assistant-text">{message.content}</p>
      {message.listings.length > 0 && (
        <div className="assistant-homes">
          {message.listings.map((home) => (
            <Link
              key={home.id}
              to={`/listings/${home.id}`}
              className="assistant-home"
            >
              <span>
                {home.city} ·{" "}
                {home.kind === "room" ? "Private room" : "Apartment"}
              </span>
              <strong>{home.title}</strong>
              <span>{home.unit_name}</span>
              <div>
                <b>
                  {money(home.monthly_rent)}
                  <small>/ month</small>
                </b>
                <ArrowUpRight size={17} />
              </div>
              <small>
                {home.available_now
                  ? "Available now · check your dates"
                  : "Check availability for your dates"}
              </small>
            </Link>
          ))}
        </div>
      )}
      {message.actions.map((action) => (
        <AssistantActionCard
          key={action.id}
          action={action}
          busy={busy}
          resolve={onAction}
        />
      ))}
    </article>
  );
}
