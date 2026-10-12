import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  Search,
  Building2,
  ClipboardCheck,
  CalendarDays,
  MessageSquare,
  FileText,
} from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import type { Statistics } from "../api/types";
import { Resource, PageTitle, money } from "../components/ui";
const labels: Record<string, string> = {
  pending_applications: "Pending applications",
  current_rentals: "Current rentals",
  future_rentals: "Upcoming rentals",
  upcoming_visits: "Upcoming visits",
  saved_listings: "Saved homes",
  unread_messages: "Unread messages",
  properties: "Properties",
  contracts: "Rental contracts",
  published_listings: "Published listings",
  users: "Registered users",
  pending_listings: "Listings to review",
  requested_visits: "Visit requests",
};
export function OverviewPage() {
  const { user } = useAuth();
  const data = useResource<Statistics>("/dashboard/statistics");
  const role = user!.role;
  const actions =
    role === "tenant"
      ? [
          [
            "/listings",
            "Find your next home",
            "Browse rooms and apartments in Italy.",
            Search,
          ],
          [
            "/tenant/applications",
            "Follow your applications",
            "See where things stand with the agency.",
            FileText,
          ],
          [
            "/tenant/messages",
            "Talk with your agency",
            "Your questions, answered in one place.",
            MessageSquare,
          ],
        ]
      : role === "landlord"
        ? [
            [
              "/landlord/properties/new",
              "Add a property",
              "Start with the place. Add the possibilities.",
              Building2,
            ],
            [
              "/landlord/properties",
              "Manage your portfolio",
              "Rooms, photos and listing reviews.",
              ClipboardCheck,
            ],
            [
              "/landlord/occupancy",
              "See the full picture",
              "Occupancy based on actual rental records.",
              CalendarDays,
            ],
          ]
        : [
            [
              "/admin/listings",
              "Review new listings",
              "Help the next home find its tenant.",
              ClipboardCheck,
            ],
            [
              "/admin/applications",
              "Manage applications",
              "Approve rentals with current availability.",
              FileText,
            ],
            [
              "/admin/messages",
              "Open the agency inbox",
              "Keep every tenant conversation moving.",
              MessageSquare,
            ],
          ];
  return (
    <>
      <PageTitle
        eyebrow={
          role === "admin" ? "The agency, at a glance" : "Your home base"
        }
        title={`Welcome back, ${user!.full_name.split(" ")[0]}.`}
        description={
          role === "tenant"
            ? "Your search, your next steps and a place to call home."
            : role === "landlord"
              ? "A clear view of your properties and the people they bring home."
              : "Everything your rental agency needs to keep things moving."
        }
      />
      <Resource value={data}>
        {(stats) => (
          <>
            <div className="stats-grid">
              {Object.entries(stats.counts).map(([key, value]) => (
                <article className="stat-card" key={key}>
                  <span>{labels[key] || key.replaceAll("_", " ")}</span>
                  <strong>{value}</strong>
                  <small>Current account records</small>
                </article>
              ))}
            </div>
            {stats.occupancy && (
              <section className="occupancy-banner">
                <div>
                  <p className="eyebrow">Portfolio occupancy</p>
                  <h2>
                    {stats.occupancy.occupancy_percent}% <span>occupied</span>
                  </h2>
                  <p>
                    {stats.occupancy.occupied_units} of{" "}
                    {stats.occupancy.total_units} physical units ·{" "}
                    {stats.occupancy.reserved_units} reserved
                  </p>
                </div>
                <div>
                  <p className="muted">Current contracted monthly rent</p>
                  <strong>
                    {money(stats.occupancy.contracted_monthly_rent)}
                  </strong>
                  <Link to={`/${role}/occupancy`} className="text-link">
                    View report
                    <ArrowRight size={16} />
                  </Link>
                </div>
              </section>
            )}
          </>
        )}
      </Resource>
      <h2 className="dashboard-section-title">What’s next?</h2>
      <div className="quick-actions">
        {actions.map(([to, title, description, Icon]) => {
          const Symbol = Icon as typeof Search;
          return (
            <Link key={String(to)} to={String(to)}>
              <div className="flex items-center justify-between">
                <Symbol size={24} strokeWidth={1.5} />
                <ArrowUpRight size={18} />
              </div>
              <h3>{String(title)}</h3>
              <p>{String(description)}</p>
            </Link>
          );
        })}
      </div>
    </>
  );
}
