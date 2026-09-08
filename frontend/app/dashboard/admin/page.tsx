"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createDepartment,
  createUser,
  deleteDepartment,
  getCurrentUser,
  getDocumentDepartments,
  listUsers,
  updateDepartment,
  updateUser,
} from "../../../lib/api";
import { getAccessToken } from "../../../lib/auth";
import type {
  Department,
  User,
  UserResponse,
} from "../../../lib/types";

const PAGE_SIZE = 20;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function actionErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Your session has expired.";
    }
    if (error.status === 403) {
      return "Administrator access is required for this action.";
    }
    if (error.status === 404) {
      return "The requested resource no longer exists.";
    }
    if (error.status === 409) {
      return error.detail || "The requested change conflicts with existing data.";
    }
    if (error.status === 422) {
      return error.detail || "Please check the submitted values.";
    }
    if (error.status === 429) {
      return "Too many requests. Please wait a moment and try again.";
    }
    return error.detail;
  }

  return error instanceof Error ? error.message : "The operation failed.";
}

export default function AdminPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [userTotal, setUserTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");

  const [departmentName, setDepartmentName] = useState("");
  const [creatingDepartment, setCreatingDepartment] = useState(false);
  const [departmentActionId, setDepartmentActionId] = useState<number | null>(
    null,
  );
  const [editingDepartmentId, setEditingDepartmentId] = useState<number | null>(
    null,
  );
  const [editingDepartmentName, setEditingDepartmentName] = useState("");

  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<"user" | "admin">("user");
  const [newUserDepartmentId, setNewUserDepartmentId] = useState<number | null>(
    null,
  );
  const [creatingUser, setCreatingUser] = useState(false);

  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editingUserEmail, setEditingUserEmail] = useState("");
  const [editingUserRole, setEditingUserRole] = useState("user");
  const [editingUserDepartmentId, setEditingUserDepartmentId] = useState<
    number | null
  >(null);
  const [userActionId, setUserActionId] = useState<number | null>(null);

  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  const departmentNameById = useMemo(
    () =>
      new Map(
        departments.map((department) => [department.id, department.name]),
      ),
    [departments],
  );

  const loadAdminData = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setPageError("");

    try {
      const currentUser = await getCurrentUser();

      if (currentUser.role !== "admin") {
        router.replace("/dashboard");
        return;
      }

      const [departmentResponse, userResponse] = await Promise.all([
        getDocumentDepartments(),
        listUsers(PAGE_SIZE, 0),
      ]);

      setUser(currentUser);
      setDepartments(departmentResponse);
      setUsers(userResponse.items);
      setUserTotal(userResponse.total);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }

      if (error instanceof ApiError && error.status === 403) {
        router.replace("/dashboard");
        return;
      }

      setPageError(
        error instanceof Error
          ? error.message
          : "Unable to load the administration workspace.",
      );
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadAdminData();
    }, 0);

    return () => window.clearTimeout(task);
  }, [loadAdminData]);

  function resetMessages() {
    setActionError("");
    setActionSuccess("");
  }

  async function handleCreateDepartment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();

    const name = departmentName.trim();

    if (!name) {
      setActionError("Department name is required.");
      return;
    }

    if (name.length > 100) {
      setActionError("Department name must be 100 characters or fewer.");
      return;
    }

    setCreatingDepartment(true);

    try {
      await createDepartment(name);
      setDepartmentName("");
      setActionSuccess(`Department "${name}" created successfully.`);
      await loadAdminData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(actionErrorMessage(error));
    } finally {
      setCreatingDepartment(false);
    }
  }

  function beginDepartmentEdit(department: Department) {
    resetMessages();
    setEditingDepartmentId(department.id);
    setEditingDepartmentName(department.name);
  }

  function cancelDepartmentEdit() {
    setEditingDepartmentId(null);
    setEditingDepartmentName("");
  }

  async function handleUpdateDepartment(departmentId: number) {
    resetMessages();

    const name = editingDepartmentName.trim();

    if (!name) {
      setActionError("Department name is required.");
      return;
    }

    if (name.length > 100) {
      setActionError("Department name must be 100 characters or fewer.");
      return;
    }

    setDepartmentActionId(departmentId);

    try {
      await updateDepartment(departmentId, name);
      cancelDepartmentEdit();
      setActionSuccess("Department updated successfully.");
      await loadAdminData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(actionErrorMessage(error));
    } finally {
      setDepartmentActionId(null);
    }
  }

  async function handleDeleteDepartment(department: Department) {
    resetMessages();

    if (
      !window.confirm(
        `Delete department "${department.name}"?\n\nThe backend will reject this if existing data still depends on it.`,
      )
    ) {
      return;
    }

    setDepartmentActionId(department.id);

    try {
      await deleteDepartment(department.id);
      setActionSuccess(`Department "${department.name}" deleted.`);
      await loadAdminData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(actionErrorMessage(error));
    } finally {
      setDepartmentActionId(null);
    }
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();

    const email = newUserEmail.trim();

    if (!email) {
      setActionError("User email is required.");
      return;
    }

    if (newUserPassword.length < 8) {
      setActionError("User password must be at least 8 characters.");
      return;
    }

    if (newUserPassword.length > 128) {
      setActionError("User password must be 128 characters or fewer.");
      return;
    }

    setCreatingUser(true);

    try {
      const created = await createUser(
        email,
        newUserPassword,
        newUserRole,
        newUserDepartmentId,
      );

      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserRole("user");
      setNewUserDepartmentId(null);
      setActionSuccess(`User ${created.email} created successfully.`);
      await loadAdminData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(actionErrorMessage(error));
    } finally {
      setCreatingUser(false);
    }
  }

  function beginUserEdit(account: UserResponse) {
    resetMessages();
    setEditingUserId(account.id);
    setEditingUserEmail(account.email);
    setEditingUserRole(account.role);
    setEditingUserDepartmentId(account.department_id);
  }

  function cancelUserEdit() {
    setEditingUserId(null);
    setEditingUserEmail("");
    setEditingUserRole("user");
    setEditingUserDepartmentId(null);
  }

  async function handleUpdateUser(userId: number) {
    resetMessages();

    const email = editingUserEmail.trim();

    if (!email) {
      setActionError("User email is required.");
      return;
    }

    if (editingUserRole.trim().length === 0) {
      setActionError("User role is required.");
      return;
    }

    setUserActionId(userId);

    try {
      const updated = await updateUser(userId, {
        email,
        role: editingUserRole.trim(),
        department_id: editingUserDepartmentId,
      });

      cancelUserEdit();
      setActionSuccess(`User ${updated.email} updated successfully.`);
      await loadAdminData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError(actionErrorMessage(error));
    } finally {
      setUserActionId(null);
    }
  }

  return (
    <div className="content-stack">
      <section className="hero-panel">
        <div>
          <div className="eyebrow">ADMINISTRATOR</div>
          <h2>Administration workspace</h2>
          <p>
            Manage departments and users through the existing administrator
            API. The backend remains authoritative for validation and access
            control.
          </p>
        </div>

        <div className="hero-security">
          <span className="security-check">✓</span>
          <div>
            <strong>Admin protected</strong>
            <span>{user?.email ?? "Administrator"}</span>
          </div>
        </div>
      </section>

      {pageError ? (
        <div className="page-alert page-alert-error" role="alert">
          <strong>Unable to load administration.</strong> {pageError}
        </div>
      ) : null}

      {actionError ? (
        <div className="page-alert page-alert-error" role="alert">
          <strong>Action failed.</strong> {actionError}
        </div>
      ) : null}

      {actionSuccess ? (
        <div className="page-alert page-alert-success" role="status">
          {actionSuccess}
        </div>
      ) : null}

      <section className="admin-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">DEPARTMENTS</div>
              <h3>Access boundaries</h3>
            </div>

            <button
              className="button button-secondary"
              type="button"
              onClick={() => void loadAdminData()}
              disabled={loading || creatingDepartment || creatingUser}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          <form className="admin-create-form" onSubmit={handleCreateDepartment}>
            <label className="field">
              <span>New department</span>
              <input
                type="text"
                value={departmentName}
                onChange={(event) => setDepartmentName(event.target.value)}
                placeholder="e.g. Legal"
                maxLength={100}
                disabled={creatingDepartment}
              />
            </label>
            <button
              className="button button-primary"
              type="submit"
              disabled={creatingDepartment}
            >
              {creatingDepartment ? "Creating…" : "Create department"}
            </button>
          </form>

          {loading ? (
            <div className="empty-state">
              <div className="spinner" aria-hidden="true" />
              <p>Loading departments…</p>
            </div>
          ) : departments.length === 0 ? (
            <div className="empty-state">
              <h4>No departments</h4>
              <p>Create the first department using the form above.</p>
            </div>
          ) : (
            <div className="admin-list">
              {departments.map((department) => {
                const busy = departmentActionId === department.id;
                const editing = editingDepartmentId === department.id;

                return (
                  <div className="admin-list-row" key={department.id}>
                    {editing ? (
                      <div className="admin-edit-stack">
                        <label className="field">
                          <span>Department name</span>
                          <input
                            type="text"
                            value={editingDepartmentName}
                            onChange={(event) =>
                              setEditingDepartmentName(event.target.value)
                            }
                            maxLength={100}
                            disabled={busy}
                          />
                        </label>
                        <div className="admin-row-actions">
                          <button
                            className="button button-small button-primary"
                            type="button"
                            onClick={() =>
                              void handleUpdateDepartment(department.id)
                            }
                            disabled={busy}
                          >
                            {busy ? "Saving…" : "Save"}
                          </button>
                          <button
                            className="button button-small button-secondary"
                            type="button"
                            onClick={cancelDepartmentEdit}
                            disabled={busy}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div>
                          <div className="document-name">{department.name}</div>
                          <div className="document-id">
                            Department #{department.id} · Created{" "}
                            {formatDate(department.created_at)}
                          </div>
                        </div>

                        <div className="admin-row-actions">
                          <button
                            className="button button-small button-secondary"
                            type="button"
                            onClick={() => beginDepartmentEdit(department)}
                            disabled={busy || departmentActionId !== null}
                          >
                            Edit
                          </button>
                          <button
                            className="button button-small button-danger"
                            type="button"
                            onClick={() => void handleDeleteDepartment(department)}
                            disabled={busy || departmentActionId !== null}
                          >
                            {busy ? "Working…" : "Delete"}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">USER CREATION</div>
              <h3>Add an account</h3>
            </div>
          </div>

          <form className="admin-form-stack" onSubmit={handleCreateUser}>
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={newUserEmail}
                onChange={(event) => setNewUserEmail(event.target.value)}
                placeholder="user@example.com"
                autoComplete="off"
                disabled={creatingUser}
              />
            </label>

            <label className="field">
              <span>Temporary password</span>
              <input
                type="password"
                value={newUserPassword}
                onChange={(event) => setNewUserPassword(event.target.value)}
                placeholder="At least 8 characters"
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                disabled={creatingUser}
              />
            </label>

            <div className="admin-form-grid">
              <label className="field">
                <span>Role</span>
                <select
                  value={newUserRole}
                  onChange={(event) =>
                    setNewUserRole(event.target.value as "user" | "admin")
                  }
                  disabled={creatingUser}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </label>

              <label className="field">
                <span>Department</span>
                <select
                  value={newUserDepartmentId ?? ""}
                  onChange={(event) =>
                    setNewUserDepartmentId(
                      event.target.value ? Number(event.target.value) : null,
                    )
                  }
                  disabled={creatingUser}
                >
                  <option value="">No department</option>
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="form-note">
              The backend requires an email, a password of at least 8
              characters, and a role. Department assignment is optional.
            </div>

            <button
              className="button button-primary"
              type="submit"
              disabled={creatingUser}
            >
              {creatingUser ? "Creating user…" : "Create user"}
            </button>
          </form>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <div className="eyebrow">USERS</div>
            <h3>Manage accounts</h3>
          </div>
          <span className="badge badge-success">
            {userTotal} total
          </span>
        </div>

        {loading ? (
          <div className="empty-state">
            <div className="spinner" aria-hidden="true" />
            <p>Loading users…</p>
          </div>
        ) : users.length === 0 ? (
          <div className="empty-state">
            <h4>No users found</h4>
            <p>Create an account using the user creation form above.</p>
          </div>
        ) : (
          <div className="admin-user-list">
            {users.map((account) => {
              const editing = editingUserId === account.id;
              const busy = userActionId === account.id;

              return (
                <div className="admin-user-row" key={account.id}>
                  {editing ? (
                    <div className="admin-user-edit">
                      <div className="admin-form-grid">
                        <label className="field">
                          <span>Email</span>
                          <input
                            type="email"
                            value={editingUserEmail}
                            onChange={(event) =>
                              setEditingUserEmail(event.target.value)
                            }
                            disabled={busy}
                          />
                        </label>

                        <label className="field">
                          <span>Role</span>
                          <input
                            type="text"
                            value={editingUserRole}
                            onChange={(event) =>
                              setEditingUserRole(event.target.value)
                            }
                            maxLength={20}
                            disabled={busy}
                          />
                        </label>
                      </div>

                      <label className="field">
                        <span>Department</span>
                        <select
                          value={editingUserDepartmentId ?? ""}
                          onChange={(event) =>
                            setEditingUserDepartmentId(
                              event.target.value
                                ? Number(event.target.value)
                                : null,
                            )
                          }
                          disabled={busy}
                        >
                          <option value="">No department</option>
                          {departments.map((department) => (
                            <option key={department.id} value={department.id}>
                              {department.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <div className="admin-row-actions">
                        <button
                          className="button button-small button-primary"
                          type="button"
                          onClick={() => void handleUpdateUser(account.id)}
                          disabled={busy}
                        >
                          {busy ? "Saving…" : "Save changes"}
                        </button>
                        <button
                          className="button button-small button-secondary"
                          type="button"
                          onClick={cancelUserEdit}
                          disabled={busy}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="admin-user-main">
                        <div className="document-name">{account.email}</div>
                        <div className="document-id">
                          User #{account.id} · Created{" "}
                          {formatDate(account.created_at)}
                        </div>
                      </div>

                      <div className="admin-user-meta">
                        <span className="badge">
                          {account.role}
                        </span>
                        <span className="badge">
                          {account.department_id !== null
                            ? departmentNameById.get(account.department_id) ??
                              `Dept #${account.department_id}`
                            : "No department"}
                        </span>
                      </div>

                      <div className="admin-row-actions">
                        <button
                          className="button button-small button-secondary"
                          type="button"
                          onClick={() => beginUserEdit(account)}
                          disabled={
                            busy ||
                            userActionId !== null ||
                            departmentActionId !== null
                          }
                        >
                          Edit
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel info-card">
        <div className="eyebrow">SECURITY NOTE</div>
        <h3>Authorization remains server-side</h3>
        <p>
          This UI only exposes administrator actions. The API still validates
          the administrator role, input constraints, relationships, and
          conflicts; the browser is not treated as a security boundary.
        </p>
      </section>
    </div>
  );
}
