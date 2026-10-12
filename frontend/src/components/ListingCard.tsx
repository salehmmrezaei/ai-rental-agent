import {
  ArrowUpRight,
  MapPin,
  BedDouble,
  Maximize2,
  Images,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { PublicListing } from "../api/types";
import { PropertyImage } from "./PropertyImage";
import { money } from "./ui";
export function ListingCard({
  listing,
  dates,
  returnTo,
}: {
  listing: PublicListing;
  dates?: string;
  returnTo?: string;
}) {
  const target = `/listings/${listing.id}${dates ? `?${dates}` : ""}`;
  return (
    <article className="listing-card">
      <Link
        to={target}
        state={returnTo ? { returnTo } : undefined}
        className="listing-photo"
        aria-label={`View ${listing.title}, ${listing.unit_name}`}
      >
        <PropertyImage image={listing.images[0]} />
        <span className="photo-tag">
          {listing.kind === "room" ? "Private room" : "Entire apartment"}
        </span>
        {listing.images.length > 0 && (
          <span className="photo-count">
            <Images size={13} />
            {listing.images.length}{" "}
            {listing.images.length === 1 ? "photo" : "photos"}
          </span>
        )}
      </Link>
      <div className="listing-card-body">
        <div className="flex items-start justify-between gap-3">
          <h3>
            <Link to={target} state={returnTo ? { returnTo } : undefined}>
              {listing.title}
            </Link>
          </h3>
          <ArrowUpRight size={19} />
        </div>
        <div className="listing-amenities">
          {listing.amenities.slice(0, 2).map((amenity) => (
            <span key={amenity}>{amenity}</span>
          ))}
        </div>
        <p className="location">
          <MapPin size={14} />
          {listing.city} · {listing.unit_name}
        </p>
        <div className="listing-features">
          <span>
            <BedDouble size={15} />
            {listing.bedrooms} {listing.bedrooms === 1 ? "bedroom" : "bedrooms"}
          </span>
          {listing.area_sqm && (
            <span>
              <Maximize2 size={15} />
              {listing.area_sqm} m²
            </span>
          )}
        </div>
        <Link
          to={target}
          state={returnTo ? { returnTo } : undefined}
          className="card-view-link"
        >
          View home <ArrowUpRight size={16} />
        </Link>
        <div className="listing-card-bottom">
          <p>
            <strong>{money(listing.monthly_rent)}</strong>
            <span> / month</span>
          </p>
          <span
            className={`availability-dot ${listing.available_now ? "is-available" : ""}`}
          >
            {listing.available_now ? "Available now" : "Check dates"}
          </span>
        </div>
      </div>
    </article>
  );
}
