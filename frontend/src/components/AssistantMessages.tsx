import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Bot, Check } from "lucide-react";
import type {
  AssistantAction,
  AssistantListing,
  AssistantMessage,
} from "../api/assistant";
import { Badge, Button, day, money, time } from "./ui";
import { useAuth } from "../auth/AuthProvider";

const actionDestinations: Record<string, [string, string]> = {
  save_listing: ["/tenant/saved", "View saved homes"],
  apply: ["/tenant/applications", "View applications"],
  withdraw_application: ["/tenant/applications", "View applications"],
  request_visit: ["/tenant/visits", "View visits"],
  cancel_visit: ["/tenant/visits", "View visits"],
  contact_agency: ["/tenant/messages", "View agency messages"],
  send_message: ["/tenant/messages", "View agency messages"],
  create_property: ["/admin/properties", "View properties"],
  update_property: ["/admin/properties", "View properties"],
  create_unit: ["/admin/properties", "View properties"],
  update_unit: ["/admin/properties", "View properties"],
  create_listing: ["/admin/listings", "View listings"],
  update_listing: ["/admin/listings", "View listings"],
  change_listing_status: ["/admin/listings", "View listings"],
  review_application: ["/admin/applications", "View applications"],
  approve_application: ["/admin/contracts", "View contracts"],
  reject_application: ["/admin/applications", "View applications"],
  update_visit: ["/admin/visits", "View visits"],
  send_tenant_message: ["/admin/messages", "View messages"],
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
  title: "Title",
  description: "Description",
  city: "City",
  address: "Address",
  postal_code: "Postal code",
  amenities: "Amenities",
  kind: "Unit type",
  name: "Unit name",
  monthly_rent: "Monthly rent",
  deposit: "Deposit",
  bedrooms: "Bedrooms",
  area_sqm: "Area (m²)",
  available_from: "Available from",
  available_until: "Available until",
  status: "New status",
  review_note: "Review note",
  scheduled_at: "Scheduled visit time",
  duration_minutes: "Duration (minutes)",
  agency_note: "Agency note",
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
  const { user } = useAuth();
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 10000);
    return () => window.clearInterval(timer);
  }, []);
  const expired = new Date(action.expires_at).getTime() <= clock;
  const destination =
    user?.role === "landlord"
      ? ["/landlord/properties", "View properties"]
      : actionDestinations[action.kind];
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
          .filter(([key]) => fieldLabels[key])
          .map(([key, value]) => (
            <div key={key}>
              <dt>{fieldLabels[key]}</dt>
              <dd>
                {value === null
                  ? key === "available_until"
                    ? "No end date"
                    : "Not set"
                  : Array.isArray(value)
                    ? value.length
                      ? value.join(", ")
                      : "None"
                    : key.endsWith("_date") ||
                        key === "available_from" ||
                        key === "available_until"
                      ? day(String(value))
                      : key === "requested_at" || key === "scheduled_at"
                        ? `${time(String(value))} (Europe/Rome)`
                        : key === "quoted_monthly_rent" ||
                            key === "monthly_rent" ||
                            key === "deposit"
                          ? `${money(String(value))}${key === "deposit" ? "" : " / month"}`
                          : String(value)}
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

function AssistantListingCard({ home }: { home: AssistantListing }) {
  const { user } = useAuth();
  const agency = user?.role === "admin" && !!home.status;
  return (
    <Link
      to={agency ? `/admin/listings/${home.id}` : `/listings/${home.id}`}
      className="assistant-home"
    >
      <span>
        {home.city} · {home.kind === "room" ? "Private room" : "Apartment"}
      </span>
      <strong>{home.title}</strong>
      <span>{home.unit_name}</span>
      {agency && (
        <div>
          <Badge value={home.status!} />
        </div>
      )}
      <div>
        <b>
          {money(home.monthly_rent)}
          <small>/ month</small>
        </b>
        <ArrowUpRight size={17} aria-hidden="true" />
      </div>
      {agency ? (
        <>
          <small>
            Available {day(home.available_from)} –{" "}
            {home.available_until ? day(home.available_until) : "No end date"}
          </small>
          <span className="text-link">Review listing</span>
        </>
      ) : (
        <small>
          {home.available_now
            ? "Available now · check your dates"
            : "Check availability for your dates"}
        </small>
      )}
    </Link>
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
            <AssistantListingCard key={home.id} home={home} />
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
