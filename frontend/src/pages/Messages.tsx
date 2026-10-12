import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Send } from "lucide-react";
import { api } from "../api/client";
import type { Conversation, Message, Page } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import {
  Button,
  Empty,
  Feedback,
  Field,
  Modal,
  PageTitle,
  Pagination,
  Resource,
  Textarea,
  formData,
  text,
  time,
} from "../components/ui";
function MessageThread({ id, onUpdate }: { id: string; onUpdate: () => void }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const action = useAction();
  const read = useAction();
  const info = useResource<Conversation>(`/conversations/${id}`);
  const messages = useResource<Page<Message>>(
    `/conversations/${id}/messages?page=${page}&page_size=30`,
  );
  const own = user!.role === "admin" ? "agency" : "tenant";
  return (
    <section className="message-thread">
      <Resource value={info}>
        {(conversation) => (
          <div className="thread-heading">
            <h2>{conversation.subject}</h2>
            {conversation.unread_count > 0 && (
              <Button
                variant="secondary"
                pending={read.pending}
                onClick={() =>
                  void read.run(async () => {
                    await api(`/conversations/${id}/read`, { method: "POST" });
                    info.reload();
                    messages.reload();
                    onUpdate();
                  })
                }
              >
                Mark {conversation.unread_count} as read
              </Button>
            )}
          </div>
        )}
      </Resource>
      <Feedback error={read.error} />
      <div className="message-history">
        <Resource value={messages}>
          {(data) => (
            <>
              {data.items.map((message) => (
                <article
                  className={`message-bubble ${message.sender_type === own ? "own" : ""}`}
                  key={message.id}
                >
                  <div className="message-meta">
                    <strong>
                      {message.sender_type === own
                        ? "You"
                        : message.sender_type === "agency"
                          ? "Your agency"
                          : "Tenant"}
                    </strong>
                    <time dateTime={message.created_at}>
                      {time(message.created_at)}
                    </time>
                  </div>
                  <p>{message.body}</p>
                  {message.sender_type === own && (
                    <small>{message.read_at ? "Read" : "Sent"}</small>
                  )}
                </article>
              ))}
              <Pagination data={data} setPage={setPage} />
            </>
          )}
        </Resource>
      </div>
      <Feedback error={action.error} />
      <form
        className="message-compose"
        onSubmit={(event) => {
          const data = formData(event);
          const form = event.currentTarget;
          void action.run(async () => {
            await api(`/conversations/${id}/messages`, {
              method: "POST",
              body: { body: text(data, "body") },
            });
            form.reset();
            setPage(
              Math.max(1, Math.ceil(((messages.data?.total || 0) + 1) / 30)),
            );
            messages.reload();
            info.reload();
            onUpdate();
          });
        }}
      >
        <Textarea
          label="Your reply"
          name="body"
          required
          maxLength={10000}
          placeholder="Write a message…"
        />
        <Button type="submit" pending={action.pending}>
          <Send size={17} />
          Send reply
        </Button>
      </form>
    </section>
  );
}
export function MessagesPage() {
  const { user } = useAuth();
  const admin = user!.role === "admin";
  const [page, setPage] = useState(1);
  const [params, setParams] = useSearchParams();
  const [compose, setCompose] = useState(false);
  const action = useAction();
  const resource = useResource<Page<Conversation>>(
    `/conversations?page=${page}&page_size=20`,
  );
  const selected = params.get("conversation");
  return (
    <>
      <PageTitle
        title={admin ? "Messaging inbox" : "Your agency messages"}
        description="A private conversation, with a person on your side."
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={resource.reload}>
              Refresh inbox
            </Button>
            {!admin && (
              <Button
                onClick={() => {
                  action.reset();
                  setCompose(true);
                }}
              >
                <Plus size={17} />
                New conversation
              </Button>
            )}
          </div>
        }
      />
      <div className="inbox-layout">
        <aside className="inbox-sidebar">
          <Resource value={resource}>
            {(data) => (
              <>
                {data.items.length ? (
                  data.items.map((item) => (
                    <button
                      className={`conversation-item ${selected === item.id ? "selected" : ""}`}
                      key={item.id}
                      onClick={() => setParams({ conversation: item.id })}
                    >
                      <strong>{item.subject}</strong>
                      <span>
                        {time(item.updated_at)}
                        {item.unread_count > 0 && (
                          <b>{item.unread_count} unread</b>
                        )}
                      </span>
                    </button>
                  ))
                ) : (
                  <Empty title="Your inbox is clear">
                    Start a conversation or wait for a tenant to get in touch.
                  </Empty>
                )}
                <Pagination data={data} setPage={setPage} />
              </>
            )}
          </Resource>
        </aside>
        {selected ? (
          <MessageThread
            key={selected}
            id={selected}
            onUpdate={resource.reload}
          />
        ) : (
          <Empty title="Every conversation starts somewhere">
            Choose a conversation to read and reply.
          </Empty>
        )}
      </div>
      {compose && (
        <Modal
          title="New agency conversation"
          onClose={() => setCompose(false)}
        >
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                const result = await api<Conversation>("/conversations", {
                  method: "POST",
                  body: {
                    subject: text(data, "subject"),
                    initial_message: text(data, "body"),
                  },
                });
                setCompose(false);
                setParams({ conversation: result.id });
                resource.reload();
              });
            }}
          >
            <Field label="Subject" name="subject" required maxLength={200} />
            <Textarea
              label="Your message"
              name="body"
              required
              maxLength={10000}
            />
            <Button type="submit" pending={action.pending}>
              Send message
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
