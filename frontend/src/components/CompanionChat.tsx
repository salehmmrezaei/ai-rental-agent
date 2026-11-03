import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowUpRight, MessageSquarePlus, Send, Sparkles } from "lucide-react";
import { api } from "../api/client";
import type {
  AssistantAction,
  AssistantListingSearchContext,
  AssistantVisitSearchContext,
  AssistantStatus,
  AssistantThread,
  AssistantThreadDetail,
} from "../api/assistant";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { beginAssistantRequest } from "../hooks/useAssistantActivity";
import { AssistantMessageView } from "./AssistantMessages";
import { Button, Feedback, Loading } from "./ui";

function restoreChat(userId: string) {
  try {
    const id = sessionStorage.getItem(`casa:blu-chat:${userId}`);
    return id && /^[a-f0-9-]{36}$/i.test(id) ? id : null;
  } catch {
    return null;
  }
}

function UserChat({
  userId,
  agency,
  landlord,
  active,
}: {
  userId: string;
  agency: boolean;
  landlord: boolean;
  active: boolean;
}) {
  const location = useLocation();
  const [chatId, setChatId] = useState<string | null>(() =>
    restoreChat(userId),
  );
  const status = useResource<AssistantStatus>("/assistant/status");
  const chats = useResource<AssistantThread[]>("/assistant/threads");
  const history = useResource<AssistantThreadDetail>(
    chatId ? `/assistant/threads/${chatId}` : null,
  );
  const [reply, setReply] = useState<AssistantThreadDetail>();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [sending, setSending] = useState("");
  const [error, setError] = useState("");
  const [listingSearchContext, setListingSearchContext] =
    useState<AssistantListingSearchContext>();
  const [visitSearchContext, setVisitSearchContext] =
    useState<AssistantVisitSearchContext>();
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const messages = useRef<HTMLDivElement>(null);
  const thread = reply || history.data;
  const available = status.data?.available === true;
  const listingId = /^\/listings\/([a-f0-9-]{36})$/i.exec(
    location.pathname,
  )?.[1];
  const propertyId =
    /^\/(?:landlord|admin)\/properties\/([a-f0-9-]{36})(?:\/edit)?$/i.exec(
      location.pathname,
    )?.[1];
  const pageContext = propertyId
    ? `Current managed property ID: ${propertyId}`
    : listingId
      ? `Current home listing ID: ${listingId}`
      : "";
  const blocked =
    !available ||
    pending ||
    (!!chatId && !thread && (history.loading || !!history.error));

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    try {
      const key = `casa:blu-chat:${userId}`;
      if (chatId) sessionStorage.setItem(key, chatId);
      else sessionStorage.removeItem(key);
    } catch {
      /* Server conversations remain available without browser storage. */
    }
  }, [chatId, userId]);
  useEffect(() => {
    if (active && available && !pending) input.current?.focus();
  }, [active, available]);
  useEffect(() => {
    if (active && messages.current)
      messages.current.scrollTop = messages.current.scrollHeight;
  }, [active, thread?.messages.length, pending]);

  function startChat(id: string | null) {
    if (pending) return;
    setChatId(id);
    setReply(undefined);
    setDraft("");
    setError("");
    setListingSearchContext(undefined);
    setVisitSearchContext(undefined);
  }

  async function send() {
    if (blocked || !draft.trim()) return;
    const submittedDraft = draft;
    const original = draft.trim();
    const latestSearch = thread?.messages.at(-1);
    const visibleVisits =
      visitSearchContext ||
      (latestSearch?.visit_search
        ? { message_id: latestSearch.id, page: latestSearch.visit_search.page }
        : undefined);
    const visibleSearch =
      listingSearchContext ||
      (latestSearch?.listing_search
        ? {
            message_id: latestSearch.id,
            page: latestSearch.listing_search.page,
          }
        : undefined);
    const message = pageContext ? `${original}\n\n${pageContext}` : original;
    if (message.length > 2000) {
      setError(
        "Please shorten your message to leave room for this property's reference.",
      );
      return;
    }
    const request = new AbortController();
    controller.current = request;
    const finishActivity = beginAssistantRequest(request.signal);
    setPending(true);
    setSending(original);
    setDraft("");
    setError("");
    try {
      const result = await api<AssistantThreadDetail>("/assistant/chat", {
        method: "POST",
        signal: request.signal,
        body: {
          message,
          thread_id: chatId,
          ...(visibleSearch && { listing_search_context: visibleSearch }),
          ...(visibleVisits && { visit_search_context: visibleVisits }),
        },
      });
      if (request.signal.aborted) return;
      const latest = result.messages.at(-1);
      if (latest?.listing_search)
        setListingSearchContext({
          message_id: latest.id,
          page: latest.listing_search.page,
        });
      if (latest?.visit_search)
        setVisitSearchContext({
          message_id: latest.id,
          page: latest.visit_search.page,
        });
      setReply(result);
      setChatId(result.id);
      chats.reload();
    } catch (cause) {
      if (!request.signal.aborted) {
        setDraft((current) => current || submittedDraft);
        setError(
          cause instanceof Error
            ? cause.message
            : "I couldn’t send that. Please try again.",
        );
        history.reload();
      }
    } finally {
      finishActivity();
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
    const finishActivity = beginAssistantRequest(request.signal);
    setPending(true);
    setError("");
    try {
      const result = await api<AssistantAction>(
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
                  item.id === result.id ? result : item,
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
            : "I couldn’t complete that action. Please try again.",
        );
        setReply(undefined);
        history.reload();
      }
    } finally {
      finishActivity();
      if (!request.signal.aborted) {
        setPending(false);
      }
    }
  }

  return (
    <div className="companion-chat">
      <div className="companion-chat-toolbar">
        <label className="sr-only" htmlFor={`blu-chats-${userId}`}>
          Blu conversation
        </label>
        <select
          id={`blu-chats-${userId}`}
          value={chatId || ""}
          disabled={pending}
          onChange={(event) => startChat(event.target.value || null)}
        >
          <option value="">New conversation</option>
          {chatId && !chats.data?.some((chat) => chat.id === chatId) && (
            <option value={chatId}>
              {thread?.title || "Current conversation"}
            </option>
          )}
          {chats.data?.map((chat) => (
            <option key={chat.id} value={chat.id}>
              {chat.title}
            </option>
          ))}
        </select>
        <button
          className="companion-new-chat"
          aria-label="New Blu chat"
          title="New chat"
          disabled={pending}
          onClick={() => startChat(null)}
        >
          <MessageSquarePlus size={17} />
        </button>
      </div>
      <Feedback error={error || status.error || history.error} />
      {status.error && (
        <Button variant="secondary" onClick={status.reload}>
          Retry connection
        </Button>
      )}
      {history.error && (
        <Button
          variant="secondary"
          onClick={() => {
            setReply(undefined);
            history.reload();
          }}
        >
          Reload conversation
        </Button>
      )}
      {status.data && !available && (
        <p className="companion-chat-notice" role="status">
          {status.data.message}
        </p>
      )}
      <div
        ref={messages}
        className="companion-chat-messages"
        role="log"
        aria-label="Conversation with Blu"
        aria-live="polite"
        aria-relevant="additions"
      >
        {status.loading || (history.loading && !thread) ? (
          <Loading label="Getting ready…" />
        ) : null}
        {!thread && !pending && (
          <div className="companion-chat-welcome">
            <span aria-hidden="true">✦</span>
            <h3>Hi, I’m Blu!</h3>
            <p>
              {agency
                ? "Your agency helper. Ask me to manage properties, listings, applications, visits, messages, or reports."
                : landlord
                  ? "Your property helper. Ask me to manage your properties, rooms, prices, listings, or occupancy reports."
                  : "Your tiny helper for finding a home. Tell me what you need — I’m all ears."}
            </p>
            <div className="companion-chat-prompts">
              {(agency
                ? [
                    "Show listings waiting for approval.",
                    "Help me create a property and its listing.",
                    "Show requested visits.",
                  ]
                : landlord
                  ? [
                      "Show my properties and draft listings.",
                      "Help me add a property and its rooms.",
                      "Give me an occupancy and contracted rent report.",
                    ]
                  : [
                      "Find rooms in Bologna under €600/month.",
                      "Check my applications.",
                      "Help me ask the agency about utilities.",
                    ]
              ).map((prompt) => (
                <button
                  key={prompt}
                  disabled={!available}
                  onClick={() => {
                    setDraft(prompt);
                    input.current?.focus();
                  }}
                >
                  {prompt}
                  <ArrowUpRight size={13} />
                </button>
              ))}
            </div>
          </div>
        )}
        {thread?.messages.map((message) => (
          <AssistantMessageView
            key={message.id}
            message={message}
            threadId={thread.id}
            onListingSearchPageChange={setListingSearchContext}
            onVisitSearchPageChange={setVisitSearchContext}
            busy={pending}
            assistantName="Blu"
            onAction={(action, confirm) => void resolve(action, confirm)}
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
                ? "Blu is checking your options…"
                : "Completing your confirmed request…"
            }
          />
        )}
      </div>
      <form
        className="companion-chat-compose"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        {pageContext && (
          <p className="companion-chat-context">
            <Sparkles size={12} />
            {propertyId
              ? "Blu can see which property you’re managing."
              : "Blu can see which home you’re viewing."}
          </p>
        )}
        <label htmlFor={`blu-message-${userId}`}>Message Blu</label>
        <div className="companion-chat-input">
          <textarea
            ref={input}
            id={`blu-message-${userId}`}
            rows={2}
            maxLength={pageContext ? 1900 : 2000}
            value={draft}
            placeholder="What can I do for you?"
            disabled={blocked}
            aria-describedby={`blu-message-hint-${userId}`}
            onChange={(event) => setDraft(event.target.value)}
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
          <button
            type="submit"
            aria-label="Send request to Blu"
            disabled={blocked || !draft.trim()}
          >
            <Send size={17} />
          </button>
        </div>
        <p className="companion-chat-privacy" id={`blu-message-hint-${userId}`}>
          Enter to send · Shift + Enter for a new line
        </p>
      </form>
    </div>
  );
}

export function CompanionChat({ active }: { active: boolean }) {
  const { user, status, refresh, error } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Loading label="Checking your account…" />;
  if (status === "error")
    return (
      <div className="companion-chat-gate">
        <Feedback error={error} />
        <Button onClick={() => void refresh()}>Retry account check</Button>
      </div>
    );
  if (user)
    return (
      <UserChat
        key={`${user.id}:${user.role}`}
        userId={user.id}
        agency={user.role === "admin"}
        landlord={user.role === "landlord"}
        active={active}
      />
    );
  return (
    <div className="companion-chat-gate">
      <Sparkles size={28} />
      <h3>Your tiny rental helper</h3>
      <p>Sign in to give Blu requests for your rental or property workspace.</p>
      {!user && (
        <Link
          className="btn btn-primary"
          to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        >
          Sign in to chat
        </Link>
      )}
    </div>
  );
}
