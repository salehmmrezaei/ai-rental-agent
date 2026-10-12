import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Plus, MapPin } from "lucide-react";
import type { Page, Property } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { PropertyImage } from "../components/PropertyImage";
import { Empty, PageTitle, Pagination, Resource } from "../components/ui";
export function PropertiesPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const resource = useResource<Page<Property>>(
    `/properties?page=${page}&page_size=12`,
  );
  const base = `/${user!.role}/properties`;
  return (
    <>
      <PageTitle
        title={
          user!.role === "admin" ? "Property management" : "Your properties"
        }
        description="Every space has a story. Manage the places in your portfolio."
        action={
          <Link to={`${base}/new`} className="btn btn-primary">
            <Plus size={17} />
            Add property
          </Link>
        }
      />
      <Resource value={resource}>
        {(data) => (
          <>
            {data.items.length ? (
              <div className="property-grid">
                {data.items.map((property) => (
                  <article className="property-card panel" key={property.id}>
                    <Link
                      to={`${base}/${property.id}`}
                      className="property-cover"
                      aria-label={`Manage ${property.title}`}
                    >
                      <PropertyImage
                        image={property.cover_image || undefined}
                        privateImage
                      />
                    </Link>
                    <p className="eyebrow">{property.city}</p>
                    <h2>
                      <Link to={`${base}/${property.id}`}>
                        {property.title}
                      </Link>
                    </h2>
                    <p className="location">
                      <MapPin size={14} />
                      {property.address}
                    </p>
                    <p className="property-description">
                      {property.description}
                    </p>
                    <Link to={`${base}/${property.id}`} className="text-link">
                      Rooms, photos & listings
                      <ArrowUpRight size={16} />
                    </Link>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="It starts with a space"
                action={
                  <Link className="btn btn-primary" to={`${base}/new`}>
                    Add your first property
                  </Link>
                }
              >
                Add a property, create its rooms or apartment, then submit a
                listing for agency review.
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
    </>
  );
}
