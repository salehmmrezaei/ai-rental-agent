import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, queryString } from "../api/client";
import type { Page, Visit } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import { AssignedAgentPicker } from "../components/UserPicker";
import {
  Badge,
  BackLink,
  Button,
  Empty,
  Feedback,
  Field,
  Modal,
  PageTitle,
  Pagination,
  Resource,
  Select,
  Textarea,
  formData,
  localDatetime,
  text,
  time,
} from "../components/ui";
export function VisitsPage() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const visitId = user?.role === "admin" ? params.get("visit") : null;
  return <VisitsWorkspace key={visitId || "queue"} visitId={visitId} />;
}

function VisitsWorkspace({ visitId }: { visitId: string | null }) {
  const { user } = useAuth();
  const admin = user!.role === "admin";
  const [page, setPage] = useState(1);
  const [period, setPeriod] = useState("all");
  const [status, setStatus] = useState("");
  const [change, setChange] = useState<{
    item: Visit;
    action: "scheduled" | "rejected" | "cancelled" | "completed";
  } | null>(null);
  const action = useAction();
  const queue = useResource<Page<Visit>>(
    visitId
      ? null
      : `/visits?${queryString({ page, status, period, page_size: 20 })}`,
  );
  const selected = useResource<Visit>(visitId ? `/visits/${visitId}` : null);
  const resource = visitId
    ? {
        ...selected,
        data: selected.data
          ? { items: [selected.data], total: 1, page: 1, page_size: 1 }
          : undefined,
      }
    : queue;
  return (
    <>
      {visitId && <BackLink to="/admin/visits">All visit requests</BackLink>}
      <PageTitle
        title={
          visitId
            ? "Review visit"
            : admin
              ? "Visit scheduling"
              : "Your property visits"
        }
        description="A closer look at the places you could call home. Times are shown in Europe/Rome."
      />
      {!visitId && (
        <div className="toolbar">
          <Select
            label="Visit period"
            value={period}
            onChange={(event) => {
              setPeriod(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">All visits</option>
            <option value="upcoming">Upcoming visits</option>
            <option value="past">Previous visits</option>
          </Select>
          <Select
            label="Visit status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {[
              "requested",
              "scheduled",
              "completed",
              "cancelled",
              "rejected",
            ].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
      )}
      <Feedback error={change ? null : action.error} success={action.success} />
      <Resource value={resource}>
        {(data) => (
          <>
            {data.items.length ? (
              <div className="record-list">
                {data.items.map((item) => (
                  <article className="record-card" key={item.id}>
                    <div className="record-top">
                      <div>
                        <h2>{item.property_title || "Property visit"}</h2>
                        <p>{item.unit_name || "Requested home"}</p>
                        {admin && item.tenant_name && (
                          <p>Tenant: {item.tenant_name}</p>
                        )}
                      </div>
                      <Badge value={item.status} />
                    </div>
                    <dl className="record-details">
                      <div>
                        <dt>Preferred visit</dt>
                        <dd>{time(item.requested_at)}</dd>
                      </div>
                      <div>
                        <dt>Scheduled visit</dt>
                        <dd>
                          {time(item.scheduled_at)}
                          {item.scheduled_at &&
                            ` · ${item.duration_minutes} minutes`}
                        </dd>
                      </div>
                    </dl>
                    {item.note && <p className="record-note">{item.note}</p>}
                    {item.agency_note && (
                      <div className="review-note">
                        <strong>Agency note</strong>
                        <p>{item.agency_note}</p>
                      </div>
                    )}
                    <div className="record-actions">
                      {admin &&
                        ["requested", "scheduled"].includes(item.status) && (
                          <Button
                            onClick={() => {
                              action.reset();
                              setChange({ item, action: "scheduled" });
                            }}
                          >
                            {item.status === "scheduled"
                              ? "Reschedule"
                              : "Schedule visit"}
                          </Button>
                        )}
                      {admin && item.status === "requested" && (
                        <Button
                          variant="danger"
                          onClick={() => {
                            action.reset();
                            setChange({ item, action: "rejected" });
                          }}
                        >
                          Reject request
                        </Button>
                      )}
                      {admin && item.status === "scheduled" && (
                        <Button
                          variant="secondary"
                          disabled={
                            !item.scheduled_end_at ||
                            new Date(item.scheduled_end_at).getTime() >
                              Date.now()
                          }
                          onClick={() => {
                            action.reset();
                            setChange({ item, action: "completed" });
                          }}
                        >
                          Mark completed
                        </Button>
                      )}
                      {["requested", "scheduled"].includes(item.status) && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            action.reset();
                            setChange({ item, action: "cancelled" });
                          }}
                        >
                          Cancel visit
                        </Button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="No visits in this view"
                action={
                  !admin && (
                    <Link className="btn btn-primary" to="/listings">
                      Explore homes
                    </Link>
                  )
                }
              >
                {admin
                  ? "New visit requests will appear here."
                  : "Request a visit from a home’s detail page or try another filter."}
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
      {change && (
        <Modal
          title={
            change.action === "scheduled"
              ? "Schedule a visit"
              : change.action === "rejected"
                ? "Reject visit request"
                : change.action === "completed"
                  ? "Complete visit"
                  : "Cancel visit"
          }
          onClose={() => setChange(null)}
        >
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                if (!admin)
                  await api(`/visits/${change.item.id}/cancel`, {
                    method: "POST",
                  });
                else {
                  const body: Record<string, string | number> = {
                    status: change.action,
                  };
                  if (change.action === "scheduled") {
                    const start = new Date(text(data, "scheduled_at"));
                    if (start.getTime() <= Date.now())
                      throw new Error("Choose a future visit time.");
                    body.scheduled_at = start.toISOString();
                    body.duration_minutes = Number(
                      text(data, "duration_minutes"),
                    );
                    body.assigned_admin_id = text(data, "assigned_admin_id");
                  }
                  if (text(data, "agency_note"))
                    body.agency_note = text(data, "agency_note");
                  await api(`/admin/visits/${change.item.id}`, {
                    method: "PATCH",
                    body,
                  });
                }
                setChange(null);
                resource.reload();
              }, "Visit updated.");
            }}
          >
            <p>
              {change.item.property_title} · {change.item.unit_name}
            </p>
            {admin && change.item.tenant_name && (
              <p>Tenant: {change.item.tenant_name}</p>
            )}
            {change.action === "scheduled" && (
              <>
                <Field
                  label="Visit time (your local time)"
                  name="scheduled_at"
                  type="datetime-local"
                  required
                  defaultValue={localDatetime(
                    change.item.scheduled_at || change.item.requested_at,
                  )}
                />
                <Field
                  label="Duration (minutes)"
                  name="duration_minutes"
                  type="number"
                  min="1"
                  max="180"
                  required
                  defaultValue={change.item.duration_minutes}
                />
                <AssignedAgentPicker
                  assignedId={change.item.assigned_admin_id}
                  current={user!}
                />
              </>
            )}
            {admin && (
              <Textarea
                label={
                  change.action === "rejected"
                    ? "Reason for rejection"
                    : "A note for the tenant (optional)"
                }
                name="agency_note"
                required={change.action === "rejected"}
                maxLength={2000}
              />
            )}
            {change.action === "cancelled" && (
              <p>
                This visit will be cancelled. You can request a new visit later.
              </p>
            )}
            <Button
              type="submit"
              pending={action.pending}
              variant={change.action === "rejected" ? "danger" : "primary"}
            >
              Confirm {change.action === "scheduled" ? "schedule" : "change"}
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
