import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { PropertyDetail } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import { UserPicker } from "../components/UserPicker";
import {
  BackLink,
  Button,
  Feedback,
  Field,
  PageTitle,
  Resource,
  Textarea,
  formData,
  text,
} from "../components/ui";
import { cities } from "../components/SearchForm";
export const frozenStatuses = [
  "submitted",
  "approved",
  "published",
  "unpublished",
];
export function propertyFrozen(property: PropertyDetail) {
  return property.units.some(
    (u) => u.listing && frozenStatuses.includes(u.listing.status),
  );
}
function PropertyForm({ initial }: { initial?: PropertyDetail }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const action = useAction();
  const frozen = initial ? propertyFrozen(initial) : false;
  return (
    <section className="panel editor-panel">
      <Feedback error={action.error} />
      {frozen && (
        <div className="notice">
          This property has reviewed listings. Unpublish and withdraw them
          before editing the property, rooms or photos.
        </div>
      )}
      <form
        className="form-stack"
        onSubmit={(event) => {
          const data = formData(event);
          void action.run(async () => {
            const amenities = text(data, "amenities")
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean);
            if (amenities.length > 20)
              throw new Error("Use no more than 20 amenities.");
            const body = {
              title: text(data, "title"),
              description: text(data, "description"),
              city: text(data, "city"),
              address: text(data, "address"),
              postal_code: text(data, "postal_code"),
              amenities,
              ...(!initial && user!.role === "admin"
                ? { landlord_id: text(data, "landlord_id") }
                : {}),
            };
            const result = await api<PropertyDetail>(
              initial ? `/properties/${initial.id}` : "/properties",
              { method: initial ? "PATCH" : "POST", body },
            );
            navigate(`/${user!.role}/properties/${result.id}`);
          });
        }}
      >
        <fieldset disabled={frozen || action.pending} className="form-stack">
          <Field
            label="Property title"
            name="title"
            required
            maxLength={200}
            defaultValue={initial?.title}
            placeholder="A welcoming apartment in Bologna"
          />
          <Textarea
            label="Description"
            name="description"
            required
            maxLength={10000}
            defaultValue={initial?.description}
          />
          <div className="form-grid">
            <Field
              label="City"
              name="city"
              list="property-cities"
              required
              maxLength={100}
              defaultValue={initial?.city}
            />
            <datalist id="property-cities">
              {cities.map((city) => (
                <option key={city}>{city}</option>
              ))}
            </datalist>
            <Field
              label="Postal code"
              name="postal_code"
              required
              pattern="[0-9]{5}"
              maxLength={5}
              defaultValue={initial?.postal_code}
              hint="Five-digit Italian postal code."
            />
          </div>
          <Field
            label="Address"
            name="address"
            required
            maxLength={300}
            defaultValue={initial?.address}
          />
          <Field
            label="Amenities"
            name="amenities"
            defaultValue={initial?.amenities.join(", ")}
            hint="Separate with commas, e.g. WiFi, balcony, lift. Up to 20."
          />
          {!initial && user!.role === "admin" && (
            <UserPicker
              role="landlord"
              name="landlord_id"
              label="Property owner"
            />
          )}
          <p className="muted">
            Development property records are marked as synthetic. Ownership is
            assigned when the property is created.
          </p>
          <Button type="submit" pending={action.pending}>
            {initial ? "Save property" : "Create property"}
          </Button>
        </fieldset>
      </form>
    </section>
  );
}
export function PropertyEditorPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const resource = useResource<PropertyDetail>(id ? `/properties/${id}` : null);
  return (
    <>
      <BackLink
        to={
          id ? `/${user!.role}/properties/${id}` : `/${user!.role}/properties`
        }
      >
        Back to {id ? "property" : "properties"}
      </BackLink>
      <PageTitle
        title={id ? "Edit property" : "Add a property"}
        description="Start with the details. Rooms and photos come next."
      />
      {id ? (
        <Resource value={resource}>
          {(property) => <PropertyForm key={property.id} initial={property} />}
        </Resource>
      ) : (
        <PropertyForm />
      )}
    </>
  );
}
