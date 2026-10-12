import { useState } from "react";
import { Link } from "react-router-dom";
import { api, queryString } from "../api/client";
import type { Application, Page } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import {
  Badge,
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
  day,
  formData,
  text,
} from "../components/ui";
export function ApplicationsPage() {
  const { user } = useAuth();
  const admin = user!.role === "admin";
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [decision, setDecision] = useState<{
    item: Application;
    action: "approve" | "reject" | "withdraw";
  } | null>(null);
  const resource = useResource<Page<Application>>(
    `/${admin ? "admin/" : ""}applications?${queryString({ page, status, page_size: 20 })}`,
  );
  const action = useAction();
  return (
    <>
      <PageTitle
        title={admin ? "Rental applications" : "Your applications"}
        description={
          admin
            ? "Review requests, check availability and help tenants take the next step."
            : "Follow every application from first request to confirmed rental."
        }
      />
      <div className="toolbar">
        <Select
          label="Application status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {["submitted", "reviewing", "approved", "rejected", "withdrawn"].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ),
          )}
        </Select>
      </div>
      <Feedback
        error={decision ? null : action.error}
        success={action.success}
      />
      <Resource value={resource}>
        {(data) => (
          <>
            {data.items.length ? (
              <div className="record-list">
                {data.items.map((item) => (
                  <article className="record-card" key={item.id}>
                    <div className="record-top">
                      <div>
                        <h2>{item.property_title || "Rental application"}</h2>
                        <p>
                          {item.unit_name || "Requested rental"} ·{" "}
                          {day(item.start_date)} – {day(item.end_date)}
                        </p>
                      </div>
                      <Badge value={item.status} />
                    </div>
                    {item.note && <p className="record-note">{item.note}</p>}
                    {item.review_note && (
                      <div className="review-note">
                        <strong>Agency note</strong>
                        <p>{item.review_note}</p>
                      </div>
                    )}
                    <div className="record-actions">
                      {admin && item.property_id && (
                        <Link
                          className="text-link"
                          to={`/admin/properties/${item.property_id}`}
                        >
                          View property
                        </Link>
                      )}
                      {admin && item.status === "submitted" && (
                        <Button
                          variant="secondary"
                          pending={action.pending}
                          onClick={() =>
                            void action.run(async () => {
                              await api(
                                `/admin/applications/${item.id}/review`,
                                { method: "POST" },
                              );
                              resource.reload();
                            }, "Application is now in review.")
                          }
                        >
                          Start review
                        </Button>
                      )}
                      {["submitted", "reviewing"].includes(item.status) &&
                        (admin ? (
                          <>
                            <Button
                              onClick={() => {
                                action.reset();
                                setDecision({ item, action: "approve" });
                              }}
                            >
                              Approve & create contract
                            </Button>
                            <Button
                              variant="danger"
                              onClick={() => {
                                action.reset();
                                setDecision({ item, action: "reject" });
                              }}
                            >
                              Reject
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="secondary"
                            onClick={() => {
                              action.reset();
                              setDecision({ item, action: "withdraw" });
                            }}
                          >
                            Withdraw application
                          </Button>
                        ))}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title={
                  admin
                    ? "No applications in this view"
                    : "Your next chapter is still open"
                }
                action={
                  !admin && (
                    <Link to="/listings" className="btn btn-primary">
                      Find a home
                    </Link>
                  )
                }
              >
                {admin
                  ? "Change the status filter or check back for new requests."
                  : "Apply from a home’s detail page to track the request here."}
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
      {decision && (
        <Modal
          title={
            decision.action === "approve"
              ? "Approve rental application"
              : decision.action === "reject"
                ? "Reject application"
                : "Withdraw application"
          }
          onClose={() => setDecision(null)}
        >
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(
                async () => {
                  const body =
                    decision.action === "reject"
                      ? { review_note: text(data, "review_note") }
                      : decision.action === "approve" &&
                          text(data, "monthly_rent")
                        ? { monthly_rent: text(data, "monthly_rent") }
                        : {};
                  const path =
                    decision.action === "withdraw"
                      ? `/applications/${decision.item.id}/withdraw`
                      : `/admin/applications/${decision.item.id}/${decision.action}`;
                  await api(path, {
                    method: "POST",
                    ...(decision.action === "withdraw" ? {} : { body }),
                  });
                  setDecision(null);
                  resource.reload();
                },
                decision.action === "approve"
                  ? "Application approved and contract created."
                  : "Application updated.",
              );
            }}
          >
            <p>
              {decision.item.property_title} · {decision.item.unit_name}
              <br />
              {day(decision.item.start_date)} – {day(decision.item.end_date)}
            </p>
            {decision.action === "approve" && (
              <>
                <Field
                  label="Monthly rent override (€, optional)"
                  name="monthly_rent"
                  type="number"
                  min="0.01"
                  max="99999999.99"
                  step="0.01"
                  hint="Leave blank to use the listing’s current rent."
                />
                <p className="muted">
                  Availability will be checked again before the contract is
                  created.
                </p>
              </>
            )}
            {decision.action === "reject" && (
              <Textarea
                label="Reason for rejection"
                name="review_note"
                required
                maxLength={2000}
              />
            )}
            {decision.action === "withdraw" && (
              <p>
                The agency will stop reviewing this request. You can submit a
                new application later.
              </p>
            )}
            <Button
              type="submit"
              pending={action.pending}
              variant={decision.action === "reject" ? "danger" : "primary"}
            >
              {decision.action === "approve"
                ? "Confirm approval"
                : decision.action === "reject"
                  ? "Confirm rejection"
                  : "Confirm withdrawal"}
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
