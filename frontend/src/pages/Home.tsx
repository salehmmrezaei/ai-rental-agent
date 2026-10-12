import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ShieldCheck,
  CalendarCheck,
  MessageCircle,
  ArrowRight,
  Building2,
} from "lucide-react";
import { SearchForm, cities } from "../components/SearchForm";
import { useResource } from "../hooks/useResource";
import type { Page, PublicListing } from "../api/types";
import { Resource, Empty } from "../components/ui";
import { ListingCard } from "../components/ListingCard";
import heroPhoto from "../assets/hero-living-v2.webp";
export function Home() {
  const listings = useResource<Page<PublicListing>>("/listings?page_size=3");
  return (
    <>
      <section className="hero-section container">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="small-dot" />
            Find your place in Italy
          </p>
          <h1>
            Your next chapter
            <br />
            starts <em>at home.</em>
          </h1>
          <p>
            From a room in Bologna to an apartment in Milan. Find a place that
            fits your life, with an agency by your side.
          </p>
          <div className="hero-shortcuts">
            <Link to="/listings?property_type=room">
              Explore private rooms <ArrowUpRight size={16} />
            </Link>
            <Link to="/listings?property_type=apartment">
              Find an apartment <ArrowUpRight size={16} />
            </Link>
          </div>
          <div className="hero-footnote">
            <ShieldCheck size={19} />
            One agency. Every step of the way.
          </div>
        </div>
        <div className="hero-art">
          <img
            src={heroPhoto}
            alt="AI-generated sample of a bright Italian apartment"
            className="hero-photo"
            fetchPriority="high"
          />
          <div className="home-photo-note">
            <span className="home-photo-icon">
              <Building2 size={22} />
            </span>
            <div>
              <strong>A space that feels like you.</strong>
              <span>Rooms & apartments, with agency support</span>
            </div>
          </div>
          <span className="hero-photo-label">Sample interior</span>
        </div>
        <div className="hero-search-wrap">
          <SearchForm />
        </div>
      </section>
      <section className="city-strip container">
        <p>
          Four cities.
          <br />
          <strong>Countless possibilities.</strong>
        </p>
        {cities.map((city, i) => (
          <Link key={city} to={`/listings?city=${city}`}>
            <span className="city-number">0{i + 1}</span>
            {city}
            <ArrowUpRight size={17} />
          </Link>
        ))}
      </section>
      <section className="section container">
        <div className="section-heading">
          <div>
            <p className="eyebrow">A fresh start</p>
            <h2>Find somewhere to belong.</h2>
          </div>
          <Link className="text-link" to="/listings">
            Explore all homes
            <ArrowRight size={18} />
          </Link>
        </div>
        <Resource value={listings}>
          {(data) =>
            data.items.length ? (
              <div className="listing-grid">
                {data.items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))}
              </div>
            ) : (
              <Empty
                title="Your next home is on its way"
                action={
                  <Link to="/listings" className="btn btn-secondary">
                    Explore all cities
                  </Link>
                }
              >
                New listings will appear here once published by the agency.
              </Empty>
            )
          }
        </Resource>
      </section>
      <section className="how-section">
        <div className="container">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Less paperwork. More possibility.</p>
              <h2>A simpler way to settle in.</h2>
            </div>
            <p>
              Everything you need,
              <br />
              in one place.
            </p>
          </div>
          <div className="steps-grid">
            {[
              [
                ShieldCheck,
                "01",
                "A home that fits",
                "Search rooms and apartments by city, budget and the dates that work for you.",
              ],
              [
                CalendarCheck,
                "02",
                "See it for yourself",
                "Request a visit and let the agency arrange a time that suits you.",
              ],
              [
                MessageCircle,
                "03",
                "A person on your side",
                "Apply online, track your rental and talk with your agency in one private inbox.",
              ],
            ].map(([Icon, n, title, copy]) => {
              const Symbol = Icon as typeof ShieldCheck;
              return (
                <article key={String(n)}>
                  <div className="step-top">
                    <Symbol size={26} strokeWidth={1.5} />
                    <span>{String(n)}</span>
                  </div>
                  <h3>{String(title)}</h3>
                  <p>{String(copy)}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>
      <section className="landlord-banner container">
        <div>
          <p className="eyebrow">For property owners</p>
          <h2>Your property. A new possibility.</h2>
          <p>Manage rooms, listings and occupancy with the agency’s support.</p>
        </div>
        <Link to="/register?role=landlord" className="btn btn-light">
          List your property
          <ArrowUpRight size={17} />
        </Link>
      </section>
    </>
  );
}
