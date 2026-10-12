import { useState } from "react";
import { useResource } from "../hooks/useResource";
import type { Page, User } from "../api/types";
import { Pagination, Resource, Select } from "./ui";
export function UserPicker({
  role,
  name,
  label,
  initial,
}: {
  role: "admin" | "landlord";
  name: string;
  label: string;
  initial?: User;
}) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(initial?.id || "");
  const [chosen, setChosen] = useState<User | undefined>(initial);
  const users = useResource<Page<User>>(
    `/admin/users?page=${page}&page_size=100`,
  );
  return (
    <div>
      <Resource value={users}>
        {(data) => {
          const items = data.items.filter(
            (u) => u.role === role && u.is_active,
          );
          if (chosen && !items.some((u) => u.id === chosen.id))
            items.unshift(chosen);
          return (
            <>
              <Select
                label={label}
                name={name}
                required
                value={selected}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setChosen(items.find((u) => u.id === event.target.value));
                }}
              >
                <option value="">
                  Choose {role === "admin" ? "an agent" : "a landlord"}
                </option>
                {items.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} · {u.email}
                  </option>
                ))}
              </Select>
              {!items.length && (
                <small className="muted">
                  No active {role === "admin" ? "agents" : "landlords"} on this
                  directory page. Check the next page.
                </small>
              )}
              <Pagination data={data} setPage={setPage} />
            </>
          );
        }}
      </Resource>
    </div>
  );
}

export function AssignedAgentPicker({
  assignedId,
  current,
}: {
  assignedId?: string | null;
  current: User;
}) {
  const previous = useResource<User>(
    assignedId && assignedId !== current.id
      ? `/admin/users/${assignedId}`
      : null,
  );
  if (assignedId && assignedId !== current.id)
    return (
      <Resource value={previous}>
        {(value) => (
          <UserPicker
            role="admin"
            label="Assigned agent"
            name="assigned_admin_id"
            initial={value.is_active ? value : current}
          />
        )}
      </Resource>
    );
  return (
    <UserPicker
      role="admin"
      label="Assigned agent"
      name="assigned_admin_id"
      initial={current}
    />
  );
}
