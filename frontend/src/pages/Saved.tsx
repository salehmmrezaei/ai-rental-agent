import { useState } from "react";
import { Link } from "react-router-dom";
import { HeartOff } from "lucide-react";
import { api } from "../api/client";
import type { Page, SavedListing } from "../api/types";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import {
  Button,
  Empty,
  Feedback,
  PageTitle,
  Pagination,
  Resource,
} from "../components/ui";
import { ListingCard } from "../components/ListingCard";
export function SavedPage() {
  const [page, setPage] = useState(1);
  const saved = useResource<Page<SavedListing>>(
    `/saved-listings?page=${page}&page_size=12`,
  );
  const action = useAction();
  return (
    <>
      <PageTitle
        title="Saved homes"
        description="The places that caught your eye. Keep them close."
      />
      <Feedback error={action.error} success={action.success} />
      <Resource value={saved}>
        {(data) => (
          <>
            {data.items.length ? (
              <div className="listing-grid">
                {data.items.map((item) => (
                  <div key={item.id} className="saved-card">
                    {item.listing ? (
                      <ListingCard listing={item.listing} />
                    ) : (
                      <div className="panel">
                        <h3>This listing is currently unavailable</h3>
                        <p className="muted">
                          It may be under review or no longer published.
                        </p>
                      </div>
                    )}
                    <Button
                      variant="ghost"
                      pending={action.pending}
                      onClick={() =>
                        void action.run(async () => {
                          await api(`/saved-listings/${item.id}`, {
                            method: "DELETE",
                          });
                          saved.reload();
                        }, "Removed from saved homes.")
                      }
                    >
                      <HeartOff size={16} />
                      Remove saved home
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="A little room for inspiration"
                action={
                  <Link to="/listings" className="btn btn-primary">
                    Explore homes
                  </Link>
                }
              >
                Save a home from its listing page to find it here later.
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
    </>
  );
}
