import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Heart,
  MapPin,
  BedDouble,
  Maximize2,
  CalendarDays,
  ArrowRight,
  Check,
} from "lucide-react";
import { api, queryString } from "../api/client";
import type { Availability, PublicListing } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import { PropertyImage } from "../components/PropertyImage";
import {
  BackLink,
  Button,
  Feedback,
  Field,
  Modal,
  Resource,
  Textarea,
  day,
  formData,
  money,
  text,
  today,
} from "../components/ui";
export function ListingDetailPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const resource = useResource<PublicListing>(`/listings/${id}`);
  const save = useAction();
  const action = useAction();
  const [modal, setModal] = useState<"apply" | "visit" | "message" | null>(
    null,
  );
  const [start, setStart] = useState(params.get("start_date") || "");
  const [end, setEnd] = useState(params.get("end_date") || "");
  const [checked, setChecked] = useState<{
    key: string;
    result: Availability;
  } | null>(null);
  const [saved, setSaved] = useState(false);
  const check = useAction();
  const key = `${start}:${end}`;
  const availability = checked?.key === key ? checked.result : null;
  function tenantAction(next: "apply" | "visit" | "message") {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/listings/${id}`)}`);
      return;
    }
    if (user.role !== "tenant") return;
    action.reset();
    setModal(next);
  }
  return (
    <div className="container detail-page">
      <BackLink to="/listings">All homes</BackLink>
      <Resource value={resource}>
        {(listing) => (
          <>
            <div className="detail-heading">
              <div>
                <p className="eyebrow">
                  {listing.kind === "room"
                    ? "A room of your own"
                    : "Space to make your own"}
                </p>
                <h1>{listing.title}</h1>
                <p className="location">
                  <MapPin size={17} />
                  {listing.address}, {listing.city} {listing.postal_code}
                </p>
                {listing.is_synthetic && (
                  <small className="synthetic-note">
                    Synthetic development property
                  </small>
                )}
              </div>
              {(!user || user.role === "tenant") && (
                <Button
                  variant="secondary"
                  pending={save.pending}
                  disabled={saved}
                  onClick={() => {
                    if (!user) {
                      navigate(
                        `/login?next=${encodeURIComponent(`/listings/${id}`)}`,
                      );
                      return;
                    }
                    void save.run(async () => {
                      await api("/saved-listings", {
                        method: "POST",
                        body: { listing_id: id },
                      });
                      setSaved(true);
                    }, "Saved to your homes.");
                  }}
                >
                  <Heart size={17} fill={saved ? "currentColor" : "none"} />
                  {saved ? "Saved" : "Save home"}
                </Button>
              )}
            </div>
            <Feedback error={save.error} success={save.success} />
            <div
              className={`detail-gallery ${listing.images.length > 1 ? "has-more" : ""}`}
            >
              <PropertyImage image={listing.images[0]} />
              {listing.images.length > 1 && (
                <div className="gallery-more">
                  {listing.images.slice(1).map((image) => (
                    <PropertyImage key={image.id} image={image} />
                  ))}
                </div>
              )}
            </div>
            <div className="detail-layout">
              <article>
                <div className="detail-facts">
                  <span>
                    <BedDouble size={20} />
                    {listing.kind === "room"
                      ? "Private room"
                      : "Entire apartment"}
                  </span>
                  <span>
                    {listing.bedrooms}{" "}
                    {listing.bedrooms === 1 ? "bedroom" : "bedrooms"}
                  </span>
                  {listing.area_sqm && (
                    <span>
                      <Maximize2 size={20} />
                      {listing.area_sqm} m²
                    </span>
                  )}
                </div>
                <h2>{listing.unit_name}</h2>
                <p className="description">{listing.description}</p>
                <h3>What’s included</h3>
                {listing.amenities.length ? (
                  <ul className="amenity-list">
                    {listing.amenities.map((amenity) => (
                      <li key={amenity}>
                        <Check size={16} />
                        {amenity}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    Ask the agency about available amenities.
                  </p>
                )}
                <h3>Availability</h3>
                <p>
                  From {day(listing.available_from)}
                  {listing.available_until
                    ? ` to ${day(listing.available_until)}`
                    : ", with an open-ended listing window"}
                  .
                </p>
                <p className="muted">
                  Select dates to check the full stay. Availability is confirmed
                  when the agency approves your application.
                </p>
                <h3>Your agency is here to help</h3>
                <p>
                  Ask a question, arrange a visit or follow your application in
                  your private workspace.
                </p>
                <Button
                  variant="secondary"
                  onClick={() => tenantAction("message")}
                  disabled={!!user && user.role !== "tenant"}
                >
                  Contact the agency
                  <ArrowRight size={16} />
                </Button>
              </article>
              <aside className="booking-panel">
                <p className="rent">
                  <strong>{money(listing.monthly_rent)}</strong> / month
                </p>
                <p className="muted">Deposit: {money(listing.deposit)}</p>
                <form
                  className="form-stack"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void check.run(async () => {
                      if (!start || !end || end <= start)
                        throw new Error(
                          "Select move-in and move-out dates in order.",
                        );
                      const result = await api<Availability>(
                        `/listings/${id}/availability?${queryString({ start_date: start, end_date: end })}`,
                      );
                      setChecked({ key, result });
                    });
                  }}
                >
                  <Field
                    label="Move-in"
                    type="date"
                    required
                    min={today()}
                    value={start}
                    onChange={(event) => setStart(event.target.value)}
                  />
                  <Field
                    label="Move-out"
                    type="date"
                    required
                    min={start || today()}
                    value={end}
                    onChange={(event) => setEnd(event.target.value)}
                  />
                  <Button
                    variant="secondary"
                    type="submit"
                    pending={check.pending}
                  >
                    Check dates
                  </Button>
                  <Feedback
                    error={check.error}
                    success={
                      availability?.available
                        ? "Available for these dates."
                        : null
                    }
                  />
                  {availability && !availability.available && (
                    <Feedback
                      error={
                        availability.reason === "rental_conflict"
                          ? "These dates overlap another rental. Try different dates."
                          : "These dates fall outside the listing window."
                      }
                    />
                  )}
                </form>
                {!user || user.role === "tenant" ? (
                  <>
                    <Button
                      onClick={() => tenantAction("apply")}
                      disabled={
                        !start ||
                        !end ||
                        end <= start ||
                        availability?.available !== true
                      }
                    >
                      Apply for this home
                      <ArrowRight size={16} />
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => tenantAction("visit")}
                    >
                      <CalendarDays size={17} />
                      Request a visit
                    </Button>
                  </>
                ) : (
                  <p className="muted">
                    Applications and visits are available to tenant accounts.
                  </p>
                )}
                <small>No payment is taken when you apply.</small>
              </aside>
            </div>
            {modal && (
              <Modal
                title={
                  modal === "apply"
                    ? "Apply for this home"
                    : modal === "visit"
                      ? "Request a visit"
                      : "Contact the agency"
                }
                onClose={() => setModal(null)}
              >
                <Feedback error={action.error} />
                <form
                  className="form-stack"
                  onSubmit={(event) => {
                    const data = formData(event);
                    void action.run(async () => {
                      if (modal === "apply") {
                        await api("/applications", {
                          method: "POST",
                          body: {
                            listing_id: id,
                            start_date: start,
                            end_date: end,
                            ...(text(data, "note")
                              ? { note: text(data, "note") }
                              : {}),
                          },
                        });
                        navigate("/tenant/applications");
                      } else if (modal === "visit") {
                        const requested = new Date(text(data, "requested_at"));
                        if (requested.getTime() <= Date.now())
                          throw new Error("Choose a future visit time.");
                        await api("/visits", {
                          method: "POST",
                          body: {
                            listing_id: id,
                            requested_at: requested.toISOString(),
                            ...(text(data, "note")
                              ? { note: text(data, "note") }
                              : {}),
                          },
                        });
                        navigate("/tenant/visits");
                      } else {
                        const body = `Regarding ${listing.title} — ${listing.unit_name}:\n\n${text(data, "body")}`;
                        await api("/conversations", {
                          method: "POST",
                          body: {
                            subject:
                              `Question about ${listing.unit_name}`.slice(
                                0,
                                200,
                              ),
                            initial_message: body,
                          },
                        });
                        navigate("/tenant/messages");
                      }
                    });
                  }}
                >
                  {modal === "apply" && (
                    <p>
                      {listing.unit_name} · {day(start)} – {day(end)}
                      <br />
                      {money(listing.monthly_rent)} / month. The agency will
                      review your application.
                    </p>
                  )}
                  {modal === "visit" && (
                    <Field
                      label="Preferred time (your local time)"
                      name="requested_at"
                      type="datetime-local"
                      required
                    />
                  )}
                  <Textarea
                    label={
                      modal === "message"
                        ? "Your message"
                        : "A note for the agency (optional)"
                    }
                    name={modal === "message" ? "body" : "note"}
                    required={modal === "message"}
                    maxLength={modal === "message" ? 9000 : 2000}
                  />
                  <Button type="submit" pending={action.pending}>
                    {modal === "apply"
                      ? "Submit application"
                      : modal === "visit"
                        ? "Send visit request"
                        : "Send message"}
                  </Button>
                </form>
              </Modal>
            )}
          </>
        )}
      </Resource>
      <Link to="/listings" className="text-link detail-bottom-link">
        Keep exploring
        <ArrowRight size={16} />
      </Link>
    </div>
  );
}
