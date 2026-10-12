import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useState } from "react";
import { Button, Field, Select, Feedback, formData, text, today } from "./ui";
import { queryString } from "../api/client";
export const cities = ["Bologna", "Milan", "Rome", "Florence"];
export function SearchForm({
  initial = new URLSearchParams(),
  compact = false,
}: {
  initial?: URLSearchParams;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className={
        compact ? "search-form filter-form" : "search-form hero-search"
      }
      onSubmit={(event) => {
        const data = formData(event);
        const start = text(data, "start_date");
        const end = text(data, "end_date");
        const min = text(data, "min_price");
        const max = text(data, "max_price");
        if (Boolean(start) !== Boolean(end) || (start && end <= start)) {
          setError("Choose both rental dates, with move-out after move-in.");
          return;
        }
        if (min && max && Number(min) > Number(max)) {
          setError("Minimum rent must not exceed maximum rent.");
          return;
        }
        setError(null);
        const values: Record<string, string> = {};
        for (const [key, value] of data.entries())
          if (String(value).trim()) values[key] = String(value).trim();
        navigate(`/listings?${queryString(values)}`);
      }}
    >
      <Select
        label="Where"
        name="city"
        defaultValue={initial.get("city") || ""}
      >
        <option value="">All cities</option>
        {cities.map((city) => (
          <option key={city}>{city}</option>
        ))}
      </Select>
      <Select
        label="Home type"
        name="property_type"
        defaultValue={initial.get("property_type") || ""}
      >
        <option value="">Rooms & apartments</option>
        <option value="room">Private room</option>
        <option value="apartment">Entire apartment</option>
      </Select>
      <Field
        label="Move-in"
        name="start_date"
        type="date"
        min={today()}
        defaultValue={initial.get("start_date") || ""}
      />
      <Field
        label="Move-out"
        name="end_date"
        type="date"
        min={today()}
        defaultValue={initial.get("end_date") || ""}
      />
      {compact && (
        <>
          <Field
            label="Min. rent (€ / month)"
            name="min_price"
            type="number"
            min="0"
            step="0.01"
            defaultValue={initial.get("min_price") || ""}
          />
          <Field
            label="Max. rent (€ / month)"
            name="max_price"
            type="number"
            min="0"
            step="0.01"
            defaultValue={initial.get("max_price") || ""}
          />
          <Select
            label="Bedrooms"
            name="min_rooms"
            defaultValue={initial.get("min_rooms") || ""}
          >
            <option value="">Any number</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option value={n} key={n}>
                {n}+
              </option>
            ))}
          </Select>
          <Select
            label="Sort by"
            name="sort"
            defaultValue={initial.get("sort") || "newest"}
          >
            <option value="newest">Newest first</option>
            <option value="price_asc">Rent: low to high</option>
            <option value="price_desc">Rent: high to low</option>
          </Select>
        </>
      )}
      <Button type="submit">
        <Search size={18} />
        {compact ? "Apply filters" : "Find your home"}
      </Button>
      <Feedback error={error} />
    </form>
  );
}
