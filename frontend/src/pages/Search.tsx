import { Link, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { SearchForm } from "../components/SearchForm";
import { ListingCard } from "../components/ListingCard";
import {
  Button,
  Empty,
  PageTitle,
  Pagination,
  Resource,
  Select,
  day,
} from "../components/ui";
import { useResource } from "../hooks/useResource";
import { queryString } from "../api/client";
import type { Page, PublicListing } from "../api/types";
export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  function filterDate(value: string | null) {
    if (
      !value ||
      !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number.isNaN(Date.parse(value))
    )
      return value || "";
    return day(value);
  }
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next);
  }
  const filterLabels: Record<string, string> = {
    city: params.get("city") || "",
    property_type:
      params.get("property_type") === "room"
        ? "Private room"
        : "Entire apartment",
    min_price: `From €${params.get("min_price")}`,
    max_price: `Up to €${params.get("max_price")}`,
    min_rooms: `${params.get("min_rooms")}+ bedrooms`,
    start_date: `${filterDate(params.get("start_date"))} – ${filterDate(params.get("end_date"))}`,
  };
  const active = Object.keys(filterLabels).filter((key) => params.get(key));
  const dates =
    params.get("start_date") && params.get("end_date")
      ? queryString({
          start_date: params.get("start_date"),
          end_date: params.get("end_date"),
        })
      : "";
  const allowed = [
    "city",
    "property_type",
    "min_price",
    "max_price",
    "min_rooms",
    "start_date",
    "end_date",
    "sort",
    "page",
  ];
  const query = Object.fromEntries(
    allowed.map((key) => [key, params.get(key)]),
  );
  const listings = useResource<Page<PublicListing>>(
    `/listings?${queryString({ ...query, page_size: 12 })}`,
  );
  return (
    <div className="container search-page">
      <PageTitle
        eyebrow="Make yourself at home"
        title={
          params.get("city")
            ? `Homes in ${params.get("city")}`
            : "Find your next home"
        }
        description="A room of your own or space for everyone. Find what feels right."
      />
      <div className="search-browse-bar">
        <div className="home-type-tabs" aria-label="Home types">
          {[
            ["", "All homes"],
            ["room", "Private rooms"],
            ["apartment", "Apartments"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={(params.get("property_type") || "") === value}
              onClick={() => update("property_type", value)}
            >
              {label}
            </button>
          ))}
        </div>
        <Button
          className="filter-toggle"
          variant="secondary"
          aria-expanded={filtersOpen}
          aria-controls="search-filters"
          onClick={() => setFiltersOpen(!filtersOpen)}
        >
          <SlidersHorizontal size={17} />
          Filters{active.length > 0 && ` (${active.length})`}
        </Button>
      </div>
      {active.length > 0 && (
        <div className="active-filters" aria-label="Active filters">
          {active.map((key) => (
            <button
              key={key}
              type="button"
              aria-label={`Remove ${filterLabels[key]} filter`}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.delete(key);
                next.delete("page");
                if (key === "start_date") next.delete("end_date");
                setParams(next);
              }}
            >
              {filterLabels[key]}
              <X size={13} />
            </button>
          ))}
          <Link to="/listings">Clear all</Link>
        </div>
      )}
      <div className="search-layout">
        <aside
          id="search-filters"
          className={`filter-panel ${filtersOpen ? "is-open" : ""}`}
        >
          <div className="flex items-center justify-between">
            <h2>Your preferences</h2>
            <Link to="/listings" className="text-link">
              Reset
            </Link>
          </div>
          <SearchForm
            compact
            initial={params}
            key={params.toString()}
            onApplied={() => {
              if (filtersOpen) window.scrollTo({ top: 0, behavior: "smooth" });
              setFiltersOpen(false);
            }}
          />
        </aside>
        <section>
          <Resource value={listings}>
            {(data) => (
              <>
                <div className="results-heading">
                  <p>
                    <strong>{data.total}</strong>{" "}
                    {data.total === 1 ? "home" : "homes"} found
                  </p>
                  <small>
                    {params.get("start_date")
                      ? "Available for your selected dates"
                      : "Choose dates to check your full stay"}
                  </small>
                  <Select
                    label="Sort by"
                    value={params.get("sort") || "newest"}
                    onChange={(event) => update("sort", event.target.value)}
                  >
                    <option value="newest">Newest first</option>
                    <option value="price_asc">Rent: low to high</option>
                    <option value="price_desc">Rent: high to low</option>
                  </Select>
                </div>
                {data.items.length ? (
                  <div className="listing-grid results-grid">
                    {data.items.map((listing) => (
                      <ListingCard
                        key={listing.id}
                        listing={listing}
                        dates={dates}
                        returnTo={`/listings?${params.toString()}`}
                      />
                    ))}
                  </div>
                ) : (
                  <Empty
                    title="No homes match just yet"
                    action={
                      <Link to="/listings" className="btn btn-secondary">
                        Clear filters
                      </Link>
                    }
                  >
                    Try another city, a wider budget or different dates.
                  </Empty>
                )}
                <Pagination
                  data={data}
                  setPage={(page) => {
                    const next = new URLSearchParams(params);
                    next.set("page", String(page));
                    setParams(next);
                  }}
                />
              </>
            )}
          </Resource>
        </section>
      </div>
    </div>
  );
}
