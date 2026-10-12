import { ArrowUpRight, MapPin, BedDouble, Maximize2 } from "lucide-react";
import { Link } from "react-router-dom";
import type { PublicListing } from "../api/types";
import { PropertyImage } from "./PropertyImage";
import { money } from "./ui";
export function ListingCard({ listing }: { listing: PublicListing }) {
  return (
    <article className="listing-card">
      <Link
        to={`/listings/${listing.id}`}
        className="listing-photo"
        aria-label={`View ${listing.title}, ${listing.unit_name}`}
      >
        <PropertyImage image={listing.images[0]} />
        <span className="photo-tag">
          {listing.kind === "room" ? "Private room" : "Entire apartment"}
        </span>
      </Link>
      <div className="listing-card-body">
        <div className="flex items-start justify-between gap-3">
          <h3>
            <Link to={`/listings/${listing.id}`}>{listing.title}</Link>
          </h3>
          <ArrowUpRight size={19} />
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
