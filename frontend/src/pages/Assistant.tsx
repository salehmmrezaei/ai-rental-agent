import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowUpRight, MessageSquarePlus, Send, Sparkles } from "lucide-react";
import { api } from "../api/client";
import type {
  AssistantAction,
  AssistantStatus,
  AssistantThread,
  AssistantThreadDetail,
} from "../api/assistant";
import { AssistantMessageView } from "../components/AssistantMessages";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import {
  Button,
  Feedback,
  Loading,
  PageTitle,
  Textarea,
} from "../components/ui";

function AssistantChat({
  chatId,
  listingId,
  propertyId,
}: {
  chatId: string | null;
  listingId: string | null;
  propertyId: string | null;
}) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const agency = user?.role === "admin";
  const landlord = user?.role === "landlord";
  const assistantPath = `/${user?.role || "tenant"}/assistant`;
  const status = useResource<AssistantStatus>("/assistant/status");
  const chats = useResource<AssistantThread[]>("/assistant/threads");
  const history = useResource<AssistantThreadDetail>(
    chatId ? `/assistant/threads/${chatId}` : null,
  );
  const [reply, setReply] = useState<AssistantThreadDetail>();
  const [draft, setDraft] = useState(
    propertyId && /^[a-f0-9-]{36}$/i.test(propertyId)
      ? `Show me this property's units, listings and rental status (property ID ${propertyId}).`
      : listingId && /^[a-f0-9-]{36}$/i.test(listingId)
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
  const blocked = pending || !available || history.loading || !!history.error;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [thread?.messages.length, pending]);

  async function send() {
    if (!draft.trim() || blocked) return;
    const submittedDraft = draft;
    const message = draft.trim();
    const request = new AbortController();
    controller.current = request;
    setPending(true);
    setSending(message);
    setDraft("");
    setError("");
    try {
      const result = await api<AssistantThreadDetail>("/assistant/chat", {
        method: "POST",
        signal: request.signal,
        body: { message, thread_id: chatId },
      });
      if (request.signal.aborted) return;
      chats.reload();
      if (!chatId)
        navigate(`${assistantPath}?chat=${result.id}`, { replace: true });
      else setReply(result);
    } catch (cause) {
      if (!request.signal.aborted) {
        setDraft((current) => current || submittedDraft);
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
        eyebrow={
          agency
            ? "Your agency workspace"
            : landlord
              ? "Your property workspace"
              : "Your rental companion"
        }
        title={
          agency
            ? "AI agency assistant"
            : landlord
              ? "AI landlord assistant"
              : "AI rental assistant"
        }
        description={
          agency
            ? "Give the agent requests to manage properties, listings, applications, visits, and messages."
            : landlord
              ? "Manage your properties, prepare listings, and understand your occupancy and rental contracts."
              : "Find a home, understand your rentals, and prepare your next step."
        }
        action={
          <Button
            variant="secondary"
            disabled={pending}
            onClick={() => {
              setReply(undefined);
              setDraft("");
              setError("");
              navigate(assistantPath);
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
                onClick={() => navigate(`${assistantPath}?chat=${chat.id}`)}
              >
                {chat.title}
              </Button>
            ))
          ) : (
            <p className="muted">Your conversations will appear here.</p>
          )}
          <Link
            className="text-link"
            to={agency || landlord ? `/${user?.role}/properties` : "/listings"}
          >
            {agency || landlord ? "View properties" : "Browse all homes"}
            <ArrowUpRight size={15} />
          </Link>
        </aside>
        <section
          className="panel assistant-chat"
          aria-label={
            agency
              ? "Agency assistant chat"
              : landlord
                ? "Landlord assistant chat"
                : "Rental assistant chat"
          }
        >
          <div className="assistant-intro">
            <span className="assistant-symbol">
              <Sparkles size={23} />
            </span>
            <div>
              <h2>
                {agency || landlord
                  ? "What would you like the agent to do?"
                  : "A little help finding your place"}
              </h2>
              <p>
                {agency
                  ? "Ask for property and listing changes, application decisions, visits, messages, or reports."
                  : landlord
                    ? "Ask me to add a property, update room prices, prepare a listing, or check occupancy and rental dates."
                    : "Ask about budget, cities, dates, or your current rentals."}{" "}
                You review and confirm every proposed action.
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
              <AssistantMessageView
                key={message.id}
                message={message}
                busy={pending}
                onAction={(a, c) => void resolve(a, c)}
              />
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
                    ? agency
                      ? "Checking agency records…"
                      : landlord
                        ? "Checking your properties…"
                        : "Checking your rental options…"
                    : "Updating your request…"
                }
              />
            )}
            <div ref={end} />
          </div>
          {!thread && !pending && (
            <div className="assistant-suggestions">
              {(agency
                ? [
                    "Show me listings waiting for approval.",
                    "Help me create a property and its listing.",
                    "Show pending applications and requested visits.",
                    "Give me an occupancy report.",
                  ]
                : landlord
                  ? [
                      "Show my properties and listings that need attention.",
                      "Help me add a property and its rooms.",
                      "Help me update a room's rent and listing dates.",
                      "Give me an occupancy and contracted rent report.",
                    ]
                  : [
                      "Find a room in Bologna under €700 a month.",
                      "What is the status of my applications?",
                      "How do I arrange a property visit?",
                    ]
              ).map((prompt) => (
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
              placeholder={
                agency || landlord
                  ? "Tell the agent what you need done…"
                  : "Tell me what you’re looking for…"
              }
              maxLength={2000}
              rows={3}
              disabled={blocked}
              aria-describedby="assistant-compose-hint"
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing &&
                  event.nativeEvent.keyCode !== 229
                ) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <div>
              <small className="muted" id="assistant-compose-hint">
                {draft.length}/2000 · Enter to send · Shift + Enter for a new
                line
              </small>
              <Button
                type="submit"
                pending={pending}
                disabled={blocked || !draft.trim()}
              >
                <Send size={16} />
                Send message
              </Button>
            </div>
          </form>
          <p className="assistant-note">
            Your chat and the rental data needed to answer it are sent to
            OpenAI. Avoid sharing passwords or payment details. AI replies can
            make mistakes; check the proposed details before confirming.
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
  const propertyId = params.get("property");
  return (
    <AssistantChat
      key={`${user?.id}:${chatId}:${listingId}:${propertyId}`}
      chatId={chatId}
      listingId={listingId}
      propertyId={propertyId}
    />
  );
}
