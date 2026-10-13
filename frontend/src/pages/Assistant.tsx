import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowUpRight,
  Bot,
  Check,
  MessageSquarePlus,
  Send,
  Sparkles,
} from "lucide-react";
import { api } from "../api/client";
import type {
  AssistantAction,
  AssistantStatus,
  AssistantThread,
  AssistantThreadDetail,
} from "../api/assistant";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import {
  Button,
  Feedback,
  Loading,
  PageTitle,
  Textarea,
  day,
  money,
  time,
} from "../components/ui";

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

function ActionCard({
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

function AssistantChat({
  chatId,
  listingId,
}: {
  chatId: string | null;
  listingId: string | null;
}) {
  const navigate = useNavigate();
  const status = useResource<AssistantStatus>("/assistant/status");
  const chats = useResource<AssistantThread[]>("/assistant/threads");
  const history = useResource<AssistantThreadDetail>(
    chatId ? `/assistant/threads/${chatId}` : null,
  );
  const [reply, setReply] = useState<AssistantThreadDetail>();
  const [draft, setDraft] = useState(
    listingId && /^[a-f0-9-]{36}$/i.test(listingId)
      ? `Tell me about this home (listing ID ${listingId}).`
      : "",
  );
  const [pending, setPending] = useState(false);
  const [sending, setSending] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const thread = reply || history.data;
  const available = status.data?.available === true;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [thread?.messages.length, pending]);

  async function send() {
    if (!draft.trim() || pending || !available) return;
    const message = draft.trim();
    const request = new AbortController();
    controller.current = request;
    setPending(true);
    setSending(message);
    setError("");
    try {
      const result = await api<AssistantThreadDetail>("/assistant/chat", {
        method: "POST",
        signal: request.signal,
        body: { message, thread_id: chatId },
      });
      if (request.signal.aborted) return;
      setDraft("");
      chats.reload();
      if (!chatId)
        navigate(`/tenant/assistant?chat=${result.id}`, { replace: true });
      else setReply(result);
    } catch (cause) {
      if (!request.signal.aborted) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to send your message.",
        );
        // Reload after uncertain network outcomes; confirmed actions remain idempotent.
        history.reload();
      }
    } finally {
      if (!request.signal.aborted) {
        setPending(false);
        setSending("");
      }
    }
  }

  async function resolve(action: AssistantAction, confirm: boolean) {
    if (pending) return;
    const request = new AbortController();
    controller.current = request;
    setPending(true);
    setError("");
    try {
      const resolved = await api<AssistantAction>(
        `/assistant/actions/${action.id}/${confirm ? "confirm" : "cancel"}`,
        {
          method: "POST",
          signal: request.signal,
          body: confirm ? { confirmed: true } : undefined,
        },
      );
      if (request.signal.aborted) return;
      setReply((current) => {
        const base = current || history.data;
        return base
          ? {
              ...base,
              messages: base.messages.map((message) => ({
                ...message,
                actions: message.actions.map((item) =>
                  item.id === resolved.id ? resolved : item,
                ),
              })),
            }
          : base;
      });
    } catch (cause) {
      if (!request.signal.aborted) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to complete this action.",
        );
        setReply(undefined);
        history.reload();
      }
    } finally {
      if (!request.signal.aborted) setPending(false);
    }
  }

  return (
    <>
      <PageTitle
        eyebrow="Your rental companion"
        title="AI rental assistant"
        description="Find a home, understand your rentals, and prepare your next step."
        action={
          <Button
            variant="secondary"
            disabled={pending}
            onClick={() => {
              setReply(undefined);
              setDraft("");
              setError("");
              navigate("/tenant/assistant");
            }}
          >
            <MessageSquarePlus size={17} />
            New chat
          </Button>
        }
      />
      <div className="assistant-layout">
        <aside className="panel assistant-chats" aria-label="Recent chats">
          <h2>Recent chats</h2>
          <Feedback error={chats.error} />
          {chats.loading ? (
            <Loading />
          ) : chats.data?.length ? (
            chats.data.map((chat) => (
              <Button
                key={chat.id}
                variant="ghost"
                disabled={pending}
                aria-current={chat.id === chatId ? "page" : undefined}
                onClick={() => navigate(`/tenant/assistant?chat=${chat.id}`)}
              >
                {chat.title}
              </Button>
            ))
          ) : (
            <p className="muted">Your conversations will appear here.</p>
          )}
          <Link className="text-link" to="/listings">
            Browse all homes
            <ArrowUpRight size={15} />
          </Link>
        </aside>
        <section
          className="panel assistant-chat"
          aria-label="Rental assistant chat"
        >
          <div className="assistant-intro">
            <span className="assistant-symbol">
              <Sparkles size={23} />
            </span>
            <div>
              <h2>A little help finding your place</h2>
              <p>
                Ask about budget, cities, dates, or your current rentals. You
                review and confirm every proposed action.
              </p>
            </div>
          </div>
          <Feedback error={status.error || history.error || error} />
          {status.loading || history.loading ? <Loading /> : null}
          {status.error && (
            <Button variant="secondary" onClick={status.reload}>
              Retry connection
            </Button>
          )}
          {history.error && (
            <Button variant="secondary" onClick={history.reload}>
              Reload chat
            </Button>
          )}
          {status.data && !available && (
            <div className="notice" role="status">
              {status.data.message}
            </div>
          )}
          <div
            className="assistant-history"
            role="log"
            aria-label="Chat messages"
            aria-live="polite"
            aria-relevant="additions"
          >
            {thread?.messages.map((message) => (
              <article
                className={`assistant-message ${message.role === "user" ? "own" : ""}`}
                key={message.id}
              >
                <p className="assistant-speaker">
                  {message.role === "user" ? (
                    "You"
                  ) : (
                    <>
                      <Bot size={16} />
                      Casa assistant
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
                  <ActionCard
                    key={action.id}
                    action={action}
                    busy={pending}
                    resolve={(a, c) => void resolve(a, c)}
                  />
                ))}
              </article>
            ))}
            {sending && (
              <article className="assistant-message own">
                <p className="assistant-speaker">You</p>
                <p className="assistant-text">{sending}</p>
              </article>
            )}
            {pending && (
              <Loading
                label={
                  sending
                    ? "Checking your rental options…"
                    : "Updating your request…"
                }
              />
            )}
            <div ref={end} />
          </div>
          {!thread && !pending && (
            <div className="assistant-suggestions">
              {[
                "Find a room in Bologna under €700 a month.",
                "What is the status of my applications?",
                "How do I arrange a property visit?",
              ].map((prompt) => (
                <Button
                  key={prompt}
                  variant="secondary"
                  disabled={!available}
                  onClick={() => setDraft(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </div>
          )}
          <form
            className="assistant-compose"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <Textarea
              label="Message the assistant"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Tell me what you’re looking for…"
              maxLength={2000}
              rows={3}
              disabled={pending || !available || !!history.error}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <div>
              <small className="muted">
                {draft.length}/2000 · Ctrl/Cmd + Enter to send
              </small>
              <Button
                type="submit"
                pending={pending}
                disabled={
                  !available ||
                  !draft.trim() ||
                  history.loading ||
                  !!history.error
                }
              >
                <Send size={16} />
                Send message
              </Button>
            </div>
          </form>
          <p className="assistant-note">
            Your chat and the rental data needed to answer it are sent to
            OpenAI. Avoid sharing passwords or payment details. AI replies can
            make mistakes; check listing details before confirming.
          </p>
        </section>
      </div>
    </>
  );
}

export function AssistantPage() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const chatId = params.get("chat");
  const listingId = params.get("listing");
  return (
    <AssistantChat
      key={`${user?.id}:${chatId}:${listingId}`}
      chatId={chatId}
      listingId={listingId}
    />
  );
}
