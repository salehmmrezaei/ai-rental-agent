import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import type {
  AssistantAction,
  AssistantListing,
  AssistantListingPage,
  AssistantListingSearchContext,
  AssistantMessage,
  AssistantVisitSearchContext,
} from "../api/assistant";
import { api } from "../api/client";
import { Badge, Button, Feedback, day, money, time } from "./ui";
import { useAuth } from "../auth/AuthProvider";
import { beginAssistantRequest } from "../hooks/useAssistantActivity";
import { AssistantVisitResults } from "./AssistantVisitResults";

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

function AssistantListingResults({
  message,
  threadId,
  busy,
  onPageChange,
}: {
  message: AssistantMessage;
  threadId?: string;
  busy: boolean;
  onPageChange?: (context: AssistantListingSearchContext) => void;
}) {
  const search = message.listing_search;
  const [results, setResults] = useState<AssistantListingPage>(() => ({
    items: message.listings,
    page: search?.page || 1,
    page_size: search?.page_size || 6,
    total: search?.total ?? message.listings.length,
  }));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const pages = Math.max(1, Math.ceil(results.total / results.page_size));

  async function changePage(page: number) {
    if (!threadId || loading || busy || page < 1 || page > pages) return;
    const request = new AbortController();
    controller.current = request;
    const finishActivity = beginAssistantRequest(request.signal);
    setLoading(true);
    setError("");
    try {
      const result = await api<AssistantListingPage>(
        `/assistant/threads/${threadId}/messages/${message.id}/listings?page=${page}`,
        { signal: request.signal },
      );
      if (request.signal.aborted) return;
      setResults(result);
      onPageChange?.({ message_id: message.id, page: result.page });
    } catch (cause) {
      if (!request.signal.aborted)
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load these homes. Please try again.",
        );
    } finally {
      finishActivity();
      if (!request.signal.aborted) setLoading(false);
    }
  }

  return (
    <div className="assistant-results" aria-busy={loading}>
      {results.items.length > 0 ? (
        <div className="assistant-homes">
          {results.items.map((home) => (
            <AssistantListingCard key={home.id} home={home} />
          ))}
        </div>
      ) : search ? (
        <p className="muted assistant-results-empty">
          {results.total === 0
            ? "No homes match these preferences. Try a different budget or rental dates."
            : "No homes on this page. Use Previous to see earlier results."}
        </p>
      ) : null}
      <Feedback error={error} />
      {search && threadId && (
        <nav
          className="assistant-results-pagination"
          aria-label="Listing search pages"
        >
          <Button
            variant="secondary"
            disabled={busy || loading || results.page <= 1}
            onClick={() => void changePage(Math.min(results.page - 1, pages))}
          >
            <ChevronLeft size={16} aria-hidden="true" />
            Previous
          </Button>
          <span className="muted" role="status" aria-live="polite">
            {loading
              ? "Loading homes…"
              : results.page > pages
                ? "Results changed"
                : `Page ${results.page} of ${pages}`}
          </span>
          <Button
            variant="secondary"
            disabled={busy || loading || results.page >= pages}
            onClick={() => void changePage(results.page + 1)}
          >
            Next
            <ChevronRight size={16} aria-hidden="true" />
          </Button>
        </nav>
      )}
    </div>
  );
}

export function AssistantMessageView({
  message,
  busy,
  onAction,
  threadId,
  onListingSearchPageChange,
  onVisitSearchPageChange,
  assistantName = "Casa assistant",
}: {
  message: AssistantMessage;
  busy: boolean;
  onAction: (action: AssistantAction, confirm: boolean) => void;
  threadId?: string;
  onListingSearchPageChange?: (context: AssistantListingSearchContext) => void;
  onVisitSearchPageChange?: (context: AssistantVisitSearchContext) => void;
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
      {!message.listing_search?.cards_only &&
        !message.visit_search?.cards_only && (
          <p className="assistant-text">{message.content}</p>
        )}
      {(message.listings.length > 0 || message.listing_search) && (
        <AssistantListingResults
          message={message}
          threadId={threadId}
          busy={busy}
          onPageChange={onListingSearchPageChange}
        />
      )}
      {message.visit_search && (
        <AssistantVisitResults
          search={message.visit_search}
          messageId={message.id}
          threadId={threadId}
          busy={busy}
          onPageChange={onVisitSearchPageChange}
        />
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
