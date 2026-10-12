import { Link, useSearchParams } from "react-router-dom";
import { SearchForm } from "../components/SearchForm";
import { ListingCard } from "../components/ListingCard";
import { Empty, PageTitle, Pagination, Resource } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { queryString } from "../api/client";
import type { Page, PublicListing } from "../api/types";
export function SearchPage() {
  const [params, setParams] = useSearchParams();
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
      <div className="search-layout">
        <aside className="filter-panel">
          <div className="flex items-center justify-between">
            <h2>Your preferences</h2>
            <Link to="/listings" className="text-link">
              Reset
            </Link>
          </div>
          <SearchForm compact initial={params} key={params.toString()} />
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
                </div>
                {data.items.length ? (
                  <div className="listing-grid results-grid">
                    {data.items.map((listing) => (
                      <ListingCard key={listing.id} listing={listing} />
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
