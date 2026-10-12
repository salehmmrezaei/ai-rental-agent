import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ShieldCheck,
  CalendarCheck,
  MessageCircle,
  ArrowRight,
} from "lucide-react";
import { SearchForm, cities } from "../components/SearchForm";
import { useResource } from "../hooks/useResource";
import type { Page, PublicListing } from "../api/types";
import { Resource, Empty } from "../components/ui";
import { ListingCard } from "../components/ListingCard";
function CityIllustration() {
  return (
    <svg viewBox="0 0 600 480" className="city-illustration" aria-hidden="true">
      <defs>
        <pattern
          id="map-grid"
          width="44"
          height="44"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M 44 0 L 0 0 0 44"
            fill="none"
            stroke="#cbd2bc"
            strokeWidth=".8"
          />
        </pattern>
      </defs>
      <rect width="600" height="480" fill="#e6eadc" />
      <rect width="600" height="480" fill="url(#map-grid)" />
      <path
        d="M-30 410L190 250 290 300 650 70M210-30L210 195 360 240 360 510"
        stroke="#f9f9f1"
        strokeWidth="30"
        fill="none"
      />
      <path
        d="M-30 410L190 250 290 300 650 70"
        stroke="#c1c9b4"
        strokeWidth="1"
        strokeDasharray="5 8"
        fill="none"
      />
      <g transform="translate(105 100)">
        <path d="M0 130L105 70 245 145 140 206Z" fill="#bcc9b4" />
        <path d="M25 102L110 53 110 164 25 213Z" fill="#decdb1" />
        <path d="M110 53L228 121 228 231 110 164Z" fill="#f2e5cc" />
        <path d="M25 102L110 53 228 121 143 169Z" fill="#a08068" />
        <path d="M25 102L143 169 143 180 25 112Z" fill="#805d49" />
        <g fill="#456355">
          <path d="M43 131L62 120 62 144 43 155Z M76 112L95 101 95 125 76 136Z M43 172L62 161 62 185 43 196Z M76 153L95 142 95 166 76 177Z" />
          <path d="M132 111L153 123 153 147 132 135Z M168 132L188 144 188 168 168 156Z M203 152L220 162 220 186 203 176Z M132 152L153 164 153 189 132 177Z M168 173L188 185 188 210 168 198Z" />
        </g>
        <path d="M200 205L216 214 216 239 200 230Z" fill="#755d4a" />
      </g>
      <g transform="translate(365 67)">
        <path d="M0 90L66 52 135 92 69 131Z" fill="#bcc9b4" />
        <path d="M10 66L68 32 68 99 10 133Z" fill="#c38f75" />
        <path d="M68 32L124 65 124 132 68 99Z" fill="#e9bfa2" />
        <path d="M10 66L65 2 124 65 68 98Z" fill="#765d4d" />
        <path d="M65 2L68 32 10 66Z" fill="#937360" />
        <path
          d="M80 75L95 84 95 103 80 94Z M105 90L117 97 117 116 105 109Z M27 77L44 67 44 85 27 95Z"
          fill="#3e6052"
        />
      </g>
      <g fill="#77976b">
        <ellipse cx="395" cy="348" rx="28" ry="17" fill="#c6d2b7" />
        <rect x="390" y="305" width="7" height="45" fill="#8a7056" />
        <circle cx="393" cy="292" r="31" />
        <rect x="79" y="304" width="6" height="37" fill="#8a7056" />
        <circle cx="82" cy="290" r="24" />
        <rect x="475" y="230" width="6" height="37" fill="#8a7056" />
        <circle cx="478" cy="217" r="24" />
      </g>
      <g transform="translate(286 134)">
        <path
          d="M0 0C-34 0-46 39-23 63L0 89 23 63C46 39 34 0 0 0"
          fill="#173f35"
        />
        <circle cy="29" r="14" fill="#f5f2e8" />
        <path d="M-7 31V24L0 19 7 24V36H-7Z" fill="#173f35" />
      </g>
      <circle cx="286" cy="227" r="12" fill="#173f35" opacity=".12" />
    </svg>
  );
}
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
          <div className="hero-footnote">
            <ShieldCheck size={19} />
            One agency. Every step of the way.
          </div>
        </div>
        <div className="hero-art">
          <CityIllustration />
          <div className="map-note">
            <span className="small-dot" />A little closer to your next home.
          </div>
          <span className="map-coordinate">44°29′ N &nbsp; 11°20′ E</span>
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
