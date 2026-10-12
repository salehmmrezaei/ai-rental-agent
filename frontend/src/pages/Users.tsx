import { useState } from "react";
import { api } from "../api/client";
import type { Page, User } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../hooks/useResource";
import { useAction } from "../hooks/useAction";
import {
  Badge,
  Button,
  Empty,
  Feedback,
  Field,
  Modal,
  PageTitle,
  Pagination,
  Resource,
  Select,
  formData,
  text,
} from "../components/ui";
export function UsersPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<User | null>(null);
  const [role, setRole] = useState("");
  const action = useAction();
  const resource = useResource<Page<User>>(
    `/admin/users?page=${page}&page_size=20`,
  );
  return (
    <>
      <PageTitle
        title="User management"
        description="The tenants, owners and agency team behind every rental."
      />
      <div className="toolbar">
        <Select
          label="Show role on this page"
          value={role}
          onChange={(event) => setRole(event.target.value)}
        >
          <option value="">All roles</option>
          {["tenant", "landlord", "admin"].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </Select>
      </div>
      <Feedback success={action.success} />
      <Resource value={resource}>
        {(data) => (
          <>
            <div className="panel table-wrap">
              <table>
                <caption className="sr-only">User directory</caption>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Account</th>
                    <th>Manage</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items
                    .filter((item) => !role || item.role === role)
                    .map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.full_name}</strong>
                        </td>
                        <td>{item.email}</td>
                        <td>
                          <Badge value={item.role} />
                        </td>
                        <td>
                          <Badge
                            value={item.is_active ? "active" : "inactive"}
                          />
                        </td>
                        <td>
                          <Button
                            aria-label={`Edit ${item.full_name}`}
                            variant="secondary"
                            onClick={() => {
                              action.reset();
                              setEditing(item);
                            }}
                          >
                            Edit
                          </Button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {!data.items.some((item) => !role || item.role === role) && (
                <Empty title="No users with this role on this page">
                  Try another directory page or clear the role filter.
                </Empty>
              )}
            </div>
            <Pagination data={data} setPage={setPage} />
          </>
        )}
      </Resource>
      {editing && (
        <Modal title="Manage user account" onClose={() => setEditing(null)}>
          <Feedback error={action.error} />
          <form
            className="form-stack"
            onSubmit={(event) => {
              const data = formData(event);
              void action.run(async () => {
                await api(`/admin/users/${editing.id}`, {
                  method: "PATCH",
                  body: {
                    full_name: text(data, "full_name"),
                    email: text(data, "email"),
                    is_active: text(data, "is_active") === "true",
                  },
                });
                setEditing(null);
                resource.reload();
              }, "Account updated.");
            }}
          >
            <Field
              label="Full name"
              name="full_name"
              required
              maxLength={150}
              defaultValue={editing.full_name}
            />
            <Field
              label="Email address"
              name="email"
              type="email"
              required
              maxLength={254}
              defaultValue={editing.email}
            />
            <Select
              label="Account access"
              name="is_active"
              defaultValue={String(editing.is_active)}
            >
              <option value="true">Active</option>
              <option value="false" disabled={editing.id === user!.id}>
                Deactivated
              </option>
            </Select>
            <p className="muted">
              Email or access changes sign the user out on every device. Roles
              are managed separately by the operator.
            </p>
            <Button type="submit" pending={action.pending}>
              Save user
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
