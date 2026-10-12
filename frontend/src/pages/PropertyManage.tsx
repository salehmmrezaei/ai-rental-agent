import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Edit3, Plus, Trash2, Camera, ArrowUpRight } from "lucide-react";
import { api } from "../api/client";
import type {
  PropertyDetail,
  PropertyImage as ImageType,
  Unit,
} from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import { PropertyImage } from "../components/PropertyImage";
import { propertyFrozen } from "./PropertyEditor";
import {
  BackLink,
  Badge,
  Button,
  Empty,
  Feedback,
  Field,
  Modal,
  PageTitle,
  Resource,
  Select,
  day,
  formData,
  money,
  text,
  today,
} from "../components/ui";
type Dialog =
  | { type: "unit"; item?: Unit }
  | { type: "listing"; item: Unit }
  | { type: "delete-unit"; item: Unit }
  | { type: "delete-property" }
  | { type: "upload" }
  | { type: "image"; item: ImageType }
  | { type: "delete-image"; item: ImageType }
  | { type: "withdraw"; item: Unit };
export function PropertyManagePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const resource = useResource<PropertyDetail>(`/properties/${id}`);
  const action = useAction();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [tab, setTab] = useState<"units" | "pictures">("units");
  const base = `/${user!.role}/properties`;
  function open(value: Dialog) {
    action.reset();
    setDialog(value);
  }
  return (
    <>
      <BackLink to={base}>All properties</BackLink>
      <Resource value={resource}>
        {(property) => {
          const frozen = propertyFrozen(property);
          return (
            <>
              <PageTitle
                eyebrow={property.city}
                title={property.title}
                description={`${property.address}, ${property.postal_code}`}
                action={
                  <div className="flex flex-wrap gap-2">
                    <Link
                      className="btn btn-secondary"
                      to={`${base}/${id}/edit`}
                    >
                      <Edit3 size={16} />
                      Edit property
                    </Link>
                    <Button
                      variant="danger"
                      disabled={frozen}
                      onClick={() => open({ type: "delete-property" })}
                    >
                      <Trash2 size={16} />
                      Delete
                    </Button>
                  </div>
                }
              />
              <p className="description">{property.description}</p>
              {property.amenities.length > 0 && (
                <div className="tag-list">
                  {property.amenities.map((a) => (
                    <span key={a}>{a}</span>
                  ))}
                </div>
              )}
              {frozen && (
                <div className="notice">
                  Reviewed listings protect the property, rooms and photos from
                  changes. Withdraw all reviewed listings to edit. Published
                  listings need agency unpublishing first.
                </div>
              )}
              <Feedback
                error={!dialog ? action.error : null}
                success={action.success}
              />
              <nav className="tabs" aria-label="Property sections">
                <button
                  className={tab === "units" ? "active" : ""}
                  aria-current={tab === "units" ? "page" : undefined}
                  onClick={() => setTab("units")}
                >
                  Rooms & listings <span>{property.units.length}</span>
                </button>
                <button
                  className={tab === "pictures" ? "active" : ""}
                  aria-current={tab === "pictures" ? "page" : undefined}
                  onClick={() => setTab("pictures")}
                >
                  Pictures <span>{property.images.length}</span>
                </button>
              </nav>
              {tab === "units" ? (
                <>
                  <div className="section-heading">
                    <div>
                      <h2>Your rental spaces</h2>
                      <p className="muted">
                        Create an entire-apartment option and independently
                        priced rooms.
                      </p>
                    </div>
                    <Button
                      disabled={frozen}
                      onClick={() => open({ type: "unit" })}
                    >
                      <Plus size={17} />
                      Add rental unit
                    </Button>
                  </div>
                  {property.units.length ? (
                    <div className="record-list">
                      {property.units.map((unit) => (
                        <article className="record-card" key={unit.id}>
                          <div className="record-top">
                            <div>
                              <p className="eyebrow">
                                {unit.kind === "room"
                                  ? "Private room"
                                  : "Entire apartment"}
                              </p>
                              <h2>{unit.name}</h2>
                            </div>
                            <Badge value={unit.occupancy_status} />
                          </div>
                          <dl className="record-details">
                            <div>
                              <dt>Monthly rent</dt>
                              <dd>{money(unit.monthly_rent)}</dd>
                            </div>
                            <div>
                              <dt>Deposit</dt>
                              <dd>{money(unit.deposit)}</dd>
                            </div>
                            <div>
                              <dt>Bedrooms</dt>
                              <dd>{unit.bedrooms}</dd>
                            </div>
                            {unit.area_sqm && (
                              <div>
                                <dt>Area</dt>
                                <dd>{unit.area_sqm} m²</dd>
                              </div>
                            )}
                          </dl>
                          <div className="unit-listing">
                            <strong>Listing</strong>
                            {unit.listing ? (
                              <>
                                <Badge value={unit.listing.status} />
                                <span>
                                  {day(unit.listing.available_from)} –{" "}
                                  {day(unit.listing.available_until)}
                                </span>
                                {unit.listing.review_note && (
                                  <p className="review-note">
                                    Agency: {unit.listing.review_note}
                                  </p>
                                )}
                              </>
                            ) : (
                              <span className="muted">Not created yet</span>
                            )}
                          </div>
                          <div className="record-actions">
                            <Button
                              variant="secondary"
                              disabled={frozen}
                              onClick={() => open({ type: "unit", item: unit })}
                            >
                              Edit unit
                            </Button>
                            <Button
                              variant="danger"
                              disabled={frozen}
                              onClick={() =>
                                open({ type: "delete-unit", item: unit })
                              }
                            >
                              Delete unit
                            </Button>
                            {(!unit.listing ||
                              unit.listing.status === "draft") && (
                              <Button
                                variant="secondary"
                                onClick={() =>
                                  open({ type: "listing", item: unit })
                                }
                              >
                                {unit.listing
                                  ? "Edit availability"
                                  : "Create listing"}
                              </Button>
                            )}
                            {unit.listing?.status === "draft" && (
                              <Button
                                pending={action.pending}
                                onClick={() =>
                                  void action.run(async () => {
                                    await api(
                                      `/listings/${unit.listing!.id}/submit`,
                                      { method: "POST" },
                                    );
                                    resource.reload();
                                  }, "Listing submitted for agency review.")
                                }
                              >
                                Submit for review
                              </Button>
                            )}
                            {unit.listing &&
                              [
                                "submitted",
                                "approved",
                                "unpublished",
                                "rejected",
                              ].includes(unit.listing.status) && (
                                <Button
                                  variant="secondary"
                                  onClick={() =>
                                    open({ type: "withdraw", item: unit })
                                  }
                                >
                                  Withdraw to draft
                                </Button>
                              )}
                            {unit.listing?.status === "published" && (
                              <>
                                <Link
                                  className="text-link"
                                  to={`/listings/${unit.listing.id}`}
                                >
                                  View public listing
                                  <ArrowUpRight size={16} />
                                </Link>
                                {user!.role === "admin" && (
                                  <Button
                                    variant="secondary"
                                    pending={action.pending}
                                    onClick={() =>
                                      void action.run(async () => {
                                        await api(
                                          `/admin/listings/${unit.listing!.id}/status`,
                                          {
                                            method: "PATCH",
                                            body: { status: "unpublished" },
                                          },
                                        );
                                        resource.reload();
                                      }, "Listing unpublished.")
                                    }
                                  >
                                    Unpublish
                                  </Button>
                                )}
                              </>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="Make room for possibilities"
                      action={
                        <Button
                          disabled={frozen}
                          onClick={() => open({ type: "unit" })}
                        >
                          Add your first unit
                        </Button>
                      }
                    >
                      Create an apartment or room and set its price.
                    </Empty>
                  )}
                </>
              ) : (
                <>
                  <div className="section-heading">
                    <div>
                      <h2>Show the space</h2>
                      <p className="muted">
                        Property photos are shared; room photos stay with the
                        right listing.
                      </p>
                    </div>
                    <Button
                      disabled={frozen}
                      onClick={() => open({ type: "upload" })}
                    >
                      <Camera size={17} />
                      Upload photo
                    </Button>
                  </div>
                  {property.images.length ? (
                    <div className="image-manager-grid">
                      {property.images.map((image) => (
                        <article
                          className="panel image-manager-card"
                          key={image.id}
                        >
                          <PropertyImage image={image} privateImage />
                          <h3>{image.alt_text}</h3>
                          <p className="muted">
                            {image.rental_unit_id
                              ? property.units.find(
                                  (u) => u.id === image.rental_unit_id,
                                )?.name || "Unit photo"
                              : "Shared property photo"}{" "}
                            · Position {image.position}
                          </p>
                          <div className="record-actions">
                            <Button
                              variant="secondary"
                              disabled={frozen}
                              onClick={() =>
                                open({ type: "image", item: image })
                              }
                            >
                              Edit photo details
                            </Button>
                            <Button
                              variant="danger"
                              disabled={frozen}
                              onClick={() =>
                                open({ type: "delete-image", item: image })
                              }
                            >
                              Delete photo
                            </Button>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="A picture makes it feel like home"
                      action={
                        <Button
                          disabled={frozen}
                          onClick={() => open({ type: "upload" })}
                        >
                          Upload a photo
                        </Button>
                      }
                    >
                      Add JPEG, PNG or WebP pictures of the property and rooms.
                    </Empty>
                  )}
                </>
              )}
              {dialog && (
                <Modal
                  title={
                    dialog.type === "unit"
                      ? dialog.item
                        ? "Edit rental unit"
                        : "Add rental unit"
                      : dialog.type === "listing"
                        ? dialog.item.listing
                          ? "Edit listing availability"
                          : "Create listing"
                        : dialog.type === "upload"
                          ? "Upload a property photo"
                          : dialog.type === "image"
                            ? "Edit photo details"
                            : dialog.type === "withdraw"
                              ? "Withdraw listing to draft"
                              : "Confirm deletion"
                  }
                  onClose={() => setDialog(null)}
                >
                  <Feedback error={action.error} />
                  <form
                    className="form-stack"
                    onSubmit={(event) => {
                      const data = formData(event);
                      void action.run(
                        async () => {
                          if (dialog.type === "unit") {
                            const body = {
                              name: text(data, "name"),
                              monthly_rent: text(data, "monthly_rent"),
                              deposit: text(data, "deposit"),
                              bedrooms: Number(text(data, "bedrooms")),
                              area_sqm: text(data, "area_sqm") || null,
                              ...(!dialog.item
                                ? { kind: text(data, "kind") }
                                : {}),
                            };
                            await api(
                              dialog.item
                                ? `/units/${dialog.item.id}`
                                : `/properties/${id}/units`,
                              { method: dialog.item ? "PATCH" : "POST", body },
                            );
                          } else if (dialog.type === "listing") {
                            const start = text(data, "available_from");
                            const end = text(data, "available_until");
                            if (end && end <= start)
                              throw new Error(
                                "Availability end must be after its start.",
                              );
                            await api(`/units/${dialog.item.id}/listing`, {
                              method: dialog.item.listing ? "PATCH" : "POST",
                              body: {
                                available_from: start,
                                available_until: end || null,
                              },
                            });
                          } else if (dialog.type === "upload") {
                            const file = data.get("file");
                            if (!(file instanceof File) || !file.size)
                              throw new Error("Choose a photo to upload.");
                            if (
                              ![
                                "image/jpeg",
                                "image/png",
                                "image/webp",
                              ].includes(file.type) ||
                              file.size > 5 * 1024 * 1024
                            )
                              throw new Error(
                                "Use a JPEG, PNG or WebP image up to 5 MB.",
                              );
                            if (!text(data, "rental_unit_id"))
                              data.delete("rental_unit_id");
                            await api(`/properties/${id}/images`, {
                              method: "POST",
                              body: data,
                            });
                          } else if (dialog.type === "image")
                            await api(
                              `/properties/${id}/images/${dialog.item.id}`,
                              {
                                method: "PATCH",
                                body: {
                                  alt_text: text(data, "alt_text"),
                                  position: Number(text(data, "position")),
                                },
                              },
                            );
                          else if (dialog.type === "delete-image")
                            await api(
                              `/properties/${id}/images/${dialog.item.id}`,
                              { method: "DELETE" },
                            );
                          else if (dialog.type === "delete-unit")
                            await api(`/units/${dialog.item.id}`, {
                              method: "DELETE",
                            });
                          else if (dialog.type === "withdraw")
                            await api(
                              `/listings/${dialog.item.listing!.id}/withdraw`,
                              { method: "POST" },
                            );
                          else {
                            await api(`/properties/${id}`, {
                              method: "DELETE",
                            });
                            navigate(base);
                            return;
                          }
                          setDialog(null);
                          resource.reload();
                        },
                        dialog.type.startsWith("delete")
                          ? "Deleted successfully."
                          : "Changes saved.",
                      );
                    }}
                  >
                    {dialog.type === "unit" && (
                      <>
                        {!dialog.item && (
                          <Select label="Rental type" name="kind">
                            <option value="room">Private room</option>
                            <option value="apartment">Entire apartment</option>
                          </Select>
                        )}
                        <Field
                          label="Unit name"
                          name="name"
                          required
                          maxLength={150}
                          defaultValue={dialog.item?.name}
                        />
                        <div className="form-grid">
                          <Field
                            label="Monthly rent (€)"
                            name="monthly_rent"
                            type="number"
                            min="0.01"
                            max="99999999.99"
                            step="0.01"
                            required
                            defaultValue={dialog.item?.monthly_rent}
                          />
                          <Field
                            label="Deposit (€)"
                            name="deposit"
                            type="number"
                            min="0"
                            max="99999999.99"
                            step="0.01"
                            required
                            defaultValue={dialog.item?.deposit || "0"}
                          />
                          <Field
                            label="Bedrooms"
                            name="bedrooms"
                            type="number"
                            min="1"
                            max="30"
                            required
                            defaultValue={dialog.item?.bedrooms || 1}
                          />
                          <Field
                            label="Area (m², optional)"
                            name="area_sqm"
                            type="number"
                            min="0.01"
                            max="999999.99"
                            step="0.01"
                            defaultValue={dialog.item?.area_sqm || ""}
                          />
                        </div>
                      </>
                    )}
                    {dialog.type === "listing" && (
                      <>
                        <Field
                          label="Available from"
                          name="available_from"
                          type="date"
                          required
                          defaultValue={
                            dialog.item.listing?.available_from || today()
                          }
                        />
                        <Field
                          label="Available until (optional)"
                          name="available_until"
                          type="date"
                          defaultValue={
                            dialog.item.listing?.available_until || ""
                          }
                        />
                        <p className="muted">
                          After saving, submit the draft listing for agency
                          review.
                        </p>
                      </>
                    )}
                    {dialog.type === "upload" && (
                      <>
                        <Field
                          label="Photo file"
                          name="file"
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          required
                          hint="JPEG, PNG or WebP, up to 5 MB."
                        />
                        <Field
                          label="Photo description"
                          name="alt_text"
                          required
                          maxLength={255}
                        />
                        <Field
                          label="Display position"
                          name="position"
                          type="number"
                          min="0"
                          max="1000"
                          defaultValue={0}
                          required
                        />
                        <Select label="Photo belongs to" name="rental_unit_id">
                          <option value="">Whole property (shared)</option>
                          {property.units.map((unit) => (
                            <option key={unit.id} value={unit.id}>
                              {unit.name}
                            </option>
                          ))}
                        </Select>
                      </>
                    )}
                    {dialog.type === "image" && (
                      <>
                        <Field
                          label="Photo description"
                          name="alt_text"
                          required
                          maxLength={255}
                          defaultValue={dialog.item.alt_text}
                        />
                        <Field
                          label="Display position"
                          name="position"
                          type="number"
                          min="0"
                          max="1000"
                          required
                          defaultValue={dialog.item.position}
                        />
                      </>
                    )}
                    {dialog.type === "withdraw" && (
                      <p>
                        The listing will return to draft and need a new review
                        before publication. You can edit the property after all
                        reviewed listings have been withdrawn.
                      </p>
                    )}
                    {dialog.type.startsWith("delete") && (
                      <p>
                        This permanently removes the{" "}
                        {dialog.type === "delete-property"
                          ? "property and its draft inventory"
                          : dialog.type === "delete-unit"
                            ? "unit and its draft listing"
                            : "photo"}
                        . Rental history or reviewed listings may prevent
                        deletion.
                      </p>
                    )}
                    <Button
                      type="submit"
                      pending={action.pending}
                      variant={
                        dialog.type.startsWith("delete") ? "danger" : "primary"
                      }
                    >
                      {dialog.type.startsWith("delete")
                        ? "Confirm deletion"
                        : dialog.type === "upload"
                          ? "Upload photo"
                          : dialog.type === "withdraw"
                            ? "Withdraw listing"
                            : "Save changes"}
                    </Button>
                  </form>
                </Modal>
              )}
            </>
          );
        }}
      </Resource>
    </>
  );
}
