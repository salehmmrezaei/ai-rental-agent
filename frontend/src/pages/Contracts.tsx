import { useState } from "react";
import { Link } from "react-router-dom";
import { api, queryString } from "../api/client";
import type { Contract, Page } from "../api/types";
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
  day,
  formData,
  money,
  text,
  today,
} from "../components/ui";
export function ContractsPage() {
  const { user } = useAuth();
  const admin = user!.role === "admin";
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [change, setChange] = useState<{
    item: Contract;
    action: string;
  } | null>(null);
  const action = useAction();
  const resource = useResource<Page<Contract>>(
    `/contracts?${queryString({ page, status, page_size: 20 })}`,
  );
  return (
    <>
      <PageTitle
        title={
          admin
            ? "Rental contracts"
            : user!.role === "landlord"
              ? "Rental history"
              : "Your rentals"
        }
        description={
          admin
            ? "Keep every agreement and its next step in view."
            : "Current, upcoming and previous rental agreements."
        }
        action={
          admin && (
            <Link to="/admin/applications" className="btn btn-primary">
              Create from an application
            </Link>
          )
        }
      />
      <div className="toolbar">
        <Select
          label="Contract status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {["confirmed", "active", "completed", "terminated", "cancelled"].map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ),
          )}
        </Select>
      </div>
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
                        <h2>{item.property_title}</h2>
                        <p>{item.unit_name}</p>
                      </div>
                      <Badge value={item.status} />
                    </div>
                    <dl className="record-details">
                      <div>
                        <dt>Rental dates</dt>
                        <dd>
                          {day(item.start_date)} – {day(item.end_date)}
                        </dd>
                      </div>
                      <div>
                        <dt>Monthly rent</dt>
                        <dd>{money(item.monthly_rent)}</dd>
                      </div>
                      {item.terminated_on && (
                        <div>
                          <dt>Effective termination</dt>
                          <dd>{day(item.terminated_on)}</dd>
                        </div>
                      )}
                    </dl>
                    {user!.role === "landlord" && (
                      <p className="muted">
                        Tenant information is kept private by the agency.
                      </p>
                    )}
                    <div className="record-actions">
                      {user!.role !== "tenant" && (
                        <Link
                          to={`/${user!.role}/properties/${item.property_id}`}
                          className="text-link"
                        >
                          View property
                        </Link>
                      )}
                      {admin && item.status === "confirmed" && (
                        <>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              action.reset();
                              setChange({ item, action: "rent" });
                            }}
                          >
                            Amend rent
                          </Button>
                          <Button
                            disabled={item.start_date > today()}
                            onClick={() => {
                              action.reset();
                              setChange({ item, action: "active" });
                            }}
                          >
                            Activate
                          </Button>
                          <Button
                            variant="danger"
                            onClick={() => {
                              action.reset();
                              setChange({ item, action: "cancelled" });
                            }}
                          >
                            Cancel contract
                          </Button>
                        </>
                      )}
                      {admin &&
                        ["confirmed", "active"].includes(item.status) && (
                          <Button
                            variant="secondary"
                            disabled={item.end_date > today()}
                            onClick={() => {
                              action.reset();
                              setChange({ item, action: "completed" });
                            }}
                          >
                            Complete
                          </Button>
                        )}
                      {admin && item.status === "active" && (
                        <Button
                          variant="danger"
                          onClick={() => {
                            action.reset();
                            setChange({ item, action: "terminated" });
                          }}
                        >
                          Terminate
                        </Button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty title="No contracts in this view">
                Confirmed rental agreements will appear here. Try a different
                status filter.
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
      {change && (
        <Modal
          title={
            change.action === "rent"
              ? "Amend monthly rent"
              : `${change.action === "active" ? "Activate" : change.action === "terminated" ? "Terminate" : change.action === "cancelled" ? "Cancel" : "Complete"} contract`
          }
          onClose={() => setChange(null)}
        >
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                const body =
                  change.action === "rent"
                    ? { monthly_rent: text(data, "monthly_rent") }
                    : {
                        status: change.action,
                        ...(change.action === "terminated"
                          ? { terminated_on: text(data, "terminated_on") }
                          : {}),
                      };
                await api(`/admin/contracts/${change.item.id}`, {
                  method: "PATCH",
                  body,
                });
                setChange(null);
                resource.reload();
              }, "Contract updated.");
            }}
          >
            <p>
              {change.item.property_title} · {change.item.unit_name}
            </p>
            {change.action === "rent" && (
              <Field
                label="Monthly rent (€)"
                name="monthly_rent"
                type="number"
                min="0.01"
                max="99999999.99"
                step="0.01"
                required
                defaultValue={change.item.monthly_rent}
              />
            )}
            {change.action === "terminated" && (
              <>
                <Field
                  label="Effective end date"
                  name="terminated_on"
                  type="date"
                  min={change.item.start_date}
                  max={change.item.end_date}
                  required
                  defaultValue={today()}
                />
                <p className="muted">
                  The original dates remain in the rental history. This
                  effective end is permanent and releases availability from that
                  date.
                </p>
              </>
            )}
            {change.action === "cancelled" && (
              <p>
                Cancelling releases all dates reserved by this contract. The
                original agreement stays in the history.
              </p>
            )}
            <Button
              type="submit"
              pending={action.pending}
              variant={
                ["terminated", "cancelled"].includes(change.action)
                  ? "danger"
                  : "primary"
              }
            >
              Confirm change
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
