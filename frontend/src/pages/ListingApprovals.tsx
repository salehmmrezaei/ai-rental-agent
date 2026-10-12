import { useState } from "react";
import { Link } from "react-router-dom";
import { api, queryString } from "../api/client";
import type { Listing, Page, Unit, PropertyDetail } from "../api/types";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import {
  Badge,
  Button,
  Empty,
  Feedback,
  Modal,
  PageTitle,
  Pagination,
  Resource,
  Select,
  Textarea,
  day,
  formData,
  money,
  text,
} from "../components/ui";
function ReviewCard({
  listing,
  onUpdate,
}: {
  listing: Listing;
  onUpdate: () => void;
}) {
  const unit = useResource<Unit>(`/units/${listing.rental_unit_id}`);
  const property = useResource<PropertyDetail>(
    unit.data ? `/properties/${unit.data.property_id}` : null,
  );
  const action = useAction();
  const [change, setChange] = useState<
    "approved" | "rejected" | "published" | "unpublished" | null
  >(null);
  return (
    <article className="record-card">
      <div className="record-top">
        <div>
          <h2>{property.data?.title || "Listing review"}</h2>
          <p>
            {unit.data?.name ||
              (unit.error ? "Unit unavailable" : "Loading unit…")}
            {unit.data && ` · ${money(unit.data.monthly_rent)} / month`}
          </p>
        </div>
        <Badge value={listing.status} />
      </div>
      <Feedback error={unit.error || property.error} />
      <p className="muted">
        Available {day(listing.available_from)} – {day(listing.available_until)}
      </p>
      {listing.review_note && (
        <div className="review-note">{listing.review_note}</div>
      )}
      <Feedback success={action.success} />
      <div className="record-actions">
        {unit.data && (
          <Link
            to={`/admin/properties/${unit.data.property_id}`}
            className="text-link"
          >
            Review property, rooms & photos
          </Link>
        )}
        {listing.status === "submitted" && (
          <>
            <Button
              onClick={() => {
                action.reset();
                setChange("approved");
              }}
            >
              Approve listing
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                action.reset();
                setChange("rejected");
              }}
            >
              Reject listing
            </Button>
          </>
        )}
        {["approved", "unpublished"].includes(listing.status) && (
          <Button
            onClick={() => {
              action.reset();
              setChange("published");
            }}
          >
            Publish listing
          </Button>
        )}
        {listing.status === "published" && (
          <>
            <Link className="text-link" to={`/listings/${listing.id}`}>
              View public listing
            </Link>
            <Button
              variant="secondary"
              onClick={() => {
                action.reset();
                setChange("unpublished");
              }}
            >
              Unpublish listing
            </Button>
          </>
        )}
      </div>
      {change && (
        <Modal
          title={`${change === "approved" ? "Approve" : change === "rejected" ? "Reject" : change === "published" ? "Publish" : "Unpublish"} listing`}
          onClose={() => setChange(null)}
        >
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                await api(`/admin/listings/${listing.id}/status`, {
                  method: "PATCH",
                  body: {
                    status: change,
                    ...(text(data, "review_note")
                      ? { review_note: text(data, "review_note") }
                      : {}),
                  },
                });
                setChange(null);
                onUpdate();
              });
            }}
          >
            <p>
              {property.data?.title} · {unit.data?.name}
            </p>
            {change === "published" && (
              <p>
                This listing will become visible in public search and accept
                tenant requests.
              </p>
            )}
            {change === "unpublished" && (
              <p>
                The listing will leave public search. Existing applications and
                contracts remain in the agency’s records.
              </p>
            )}
            <Textarea
              label={
                change === "rejected"
                  ? "Reason for rejection"
                  : "Review note (optional)"
              }
              name="review_note"
              required={change === "rejected"}
              maxLength={2000}
            />
            <Button
              type="submit"
              pending={action.pending}
              variant={change === "rejected" ? "danger" : "primary"}
            >
              Confirm{" "}
              {change === "approved"
                ? "approval"
                : change === "rejected"
                  ? "rejection"
                  : change === "published"
                    ? "publication"
                    : "unpublishing"}
            </Button>
          </form>
        </Modal>
      )}
    </article>
  );
}
export function ListingApprovalsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("submitted");
  const resource = useResource<Page<Listing>>(
    `/admin/listings?${queryString({ page, status, page_size: 20 })}`,
  );
  return (
    <>
      <PageTitle
        title="Listing approvals"
        description="Review each space, then help it find the right tenant."
      />
      <div className="toolbar">
        <Select
          label="Listing status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {[
            "draft",
            "submitted",
            "approved",
            "rejected",
            "published",
            "unpublished",
          ].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </div>
      <Resource value={resource}>
        {(data) => (
          <>
            {data.items.length ? (
              <div className="record-list">
                {data.items.map((listing) => (
                  <ReviewCard
                    key={listing.id}
                    listing={listing}
                    onUpdate={resource.reload}
                  />
                ))}
              </div>
            ) : (
              <Empty title="No listings in this view">
                New submissions will appear here. Change the filter to review
                other listing statuses.
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
    </>
  );
}
