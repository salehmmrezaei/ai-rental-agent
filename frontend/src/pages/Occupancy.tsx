import { useState } from "react";
import { Link } from "react-router-dom";
import { queryString } from "../api/client";
import type { OccupancyReport } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import {
  Empty,
  Field,
  PageTitle,
  Pagination,
  Resource,
  money,
  today,
} from "../components/ui";
export function OccupancyPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [date, setDate] = useState(today());
  const report = useResource<OccupancyReport>(
    `/occupancy?${queryString({ page, as_of: date || today(), page_size: 20 })}`,
  );
  return (
    <>
      <PageTitle
        title="Occupancy overview"
        description="The full picture, drawn from actual rental agreements."
      />
      <div className="toolbar">
        <Field
          label="Report date"
          type="date"
          required
          value={date}
          onChange={(event) => {
            setDate(event.target.value);
            setPage(1);
          }}
        />
      </div>
      <Resource value={report}>
        {(data) => (
          <>
            <div className="stats-grid">
              <article className="stat-card">
                <span>Occupancy</span>
                <strong>{data.summary.occupancy_percent}%</strong>
                <small>
                  {data.summary.occupied_units} of {data.summary.total_units}{" "}
                  units
                </small>
              </article>
              <article className="stat-card">
                <span>Available units</span>
                <strong>{data.summary.available_units}</strong>
                <small>On the selected date</small>
              </article>
              <article className="stat-card">
                <span>Reserved units</span>
                <strong>{data.summary.reserved_units}</strong>
                <small>Future rental agreements</small>
              </article>
              <article className="stat-card">
                <span>Contracted monthly rent</span>
                <strong className="stat-money">
                  {money(data.summary.contracted_monthly_rent)}
                </strong>
                <small>Current contracts, before any collections</small>
              </article>
            </div>
            {data.items.length ? (
              <div className="panel table-wrap">
                <table>
                  <caption className="sr-only">Occupancy by property</caption>
                  <thead>
                    <tr>
                      <th>Property</th>
                      <th>Units</th>
                      <th>Occupied</th>
                      <th>Reserved</th>
                      <th>Available</th>
                      <th>Occupancy</th>
                      <th>Monthly rent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.property_id}>
                        <td>
                          <Link
                            className="text-link"
                            to={`/${user!.role}/properties/${item.property_id}`}
                          >
                            {item.title}
                          </Link>
                          <small>{item.city}</small>
                        </td>
                        <td>{item.total_units}</td>
                        <td>{item.occupied_units}</td>
                        <td>{item.reserved_units}</td>
                        <td>{item.available_units}</td>
                        <td>
                          <div className="occupancy-meter">
                            <span
                              style={{ width: `${item.occupancy_percent}%` }}
                            />
                          </div>
                          {item.occupancy_percent}%
                        </td>
                        <td>{money(item.contracted_monthly_rent)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="A portfolio ready to grow">
                Add a property to begin tracking occupancy.
              </Empty>
            )}
            <Pagination data={data} setPage={setPage} />
            <p className="report-note">
              Rooms count as physical units; an apartment listing is an
              alternative rental option. A whole-apartment contract occupies its
              rooms and contributes rent once. Contracted rent is not collected
              revenue.
            </p>
          </>
        )}
      </Resource>
    </>
  );
}
