import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "../api/client";
import type {
  AssistantVisitPage,
  AssistantVisitSearch,
  AssistantVisitSearchContext,
} from "../api/assistant";
import { beginAssistantRequest } from "../hooks/useAssistantActivity";
import { Badge, Button, Feedback, time } from "./ui";

export function AssistantVisitResults({
  search,
  messageId,
  threadId,
  busy,
  onPageChange,
}: {
  search: AssistantVisitSearch;
  messageId: string;
  threadId?: string;
  busy: boolean;
  onPageChange?: (context: AssistantVisitSearchContext) => void;
}) {
  const [results, setResults] = useState<AssistantVisitPage>(search);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const pages = Math.max(1, Math.ceil(results.total / results.page_size));

  async function changePage(page: number) {
    if (!threadId || busy || loading || page < 1 || page > pages) return;
    const request = new AbortController();
    controller.current = request;
    const finish = beginAssistantRequest(request.signal);
    setLoading(true);
    setError("");
    try {
      const result = await api<AssistantVisitPage>(
        `/assistant/threads/${threadId}/messages/${messageId}/visits?page=${page}`,
        { signal: request.signal },
      );
      if (request.signal.aborted) return;
      setResults(result);
      onPageChange?.({ message_id: messageId, page: result.page });
    } catch (cause) {
      if (!request.signal.aborted)
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load these visits. Please try again.",
        );
    } finally {
      finish();
      if (!request.signal.aborted) setLoading(false);
    }
  }

  return (
    <div className="assistant-results" aria-busy={loading}>
      <p className="assistant-results-summary">
        {results.total} visit {results.total === 1 ? "request" : "requests"}
      </p>
      {results.items.length > 0 ? (
        <div className="assistant-homes">
          {results.items.map((visit) => (
            <Link
              key={visit.id}
              to={`/admin/visits?visit=${visit.id}`}
              className="assistant-home assistant-visit"
            >
              <strong>{visit.property_title}</strong>
              <span>{visit.unit_name}</span>
              <span>Tenant: {visit.tenant_name}</span>
              <div>
                <Badge value={visit.status} />
              </div>
              <small>
                Preferred visit: {time(visit.requested_at)} (Europe/Rome)
              </small>
              {visit.scheduled_at && (
                <small>
                  Scheduled: {time(visit.scheduled_at)} ·{" "}
                  {visit.duration_minutes} minutes (Europe/Rome)
                </small>
              )}
              {visit.note && (
                <p className="assistant-visit-note">{visit.note}</p>
              )}
              <div className="text-link">
                {visit.status === "requested"
                  ? "Review & schedule"
                  : "Review visit"}
                <ArrowUpRight size={17} aria-hidden="true" />
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="muted assistant-results-empty">
          {results.total === 0
            ? "No visit requests match this view."
            : "No visits on this page. Use Previous to see earlier requests."}
        </p>
      )}
      <Feedback error={error} />
      {threadId && (
        <nav
          className="assistant-results-pagination"
          aria-label="Visit request pages"
        >
          <Button
            variant="secondary"
            disabled={busy || loading || results.page <= 1}
            onClick={() => void changePage(Math.min(results.page - 1, pages))}
          >
            <ChevronLeft size={16} aria-hidden="true" /> Previous
          </Button>
          <span className="muted" role="status" aria-live="polite">
            {loading
              ? "Loading visits…"
              : results.page > pages
                ? "Results changed"
                : `Page ${results.page} of ${pages}`}
          </span>
          <Button
            variant="secondary"
            disabled={busy || loading || results.page >= pages}
            onClick={() => void changePage(results.page + 1)}
          >
            Next <ChevronRight size={16} aria-hidden="true" />
          </Button>
        </nav>
      )}
    </div>
  );
}
