"use client";

import {
  ChangeEvent,
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  deleteDocument,
  getCurrentUser,
  getDocumentDepartments,
  listDocuments,
  reindexDocument,
  uploadDocument,
} from "../../lib/api";
import { getAccessToken } from "../../lib/auth";
import type { Department, Document, User } from "../../lib/types";

const MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".docx"] as const;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusClass(status: string): string {
  switch (status.toLowerCase()) {
    case "indexed":
      return "badge badge-success";
    case "processing":
    case "uploaded":
    case "deleting":
      return "badge badge-warning";
    case "failed":
      return "badge badge-danger";
    default:
      return "badge";
  }
}

function fileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  return lastDot >= 0 ? filename.slice(lastDot).toLowerCase() : "";
}

function uploadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Only administrators can upload documents.";
    }

    if (error.status === 413) {
      return "The selected file is too large.";
    }

    if (error.status === 429) {
      return "Upload rate limit reached. Please wait a moment and try again.";
    }

    if (error.status === 503) {
      return error.detail || "The document service is temporarily unavailable.";
    }

    return error.detail;
  }

  return error instanceof Error
    ? error.message
    : "Unable to upload the document.";
}

function actionErrorMessage(action: "reindex" | "delete", error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Only administrators can manage documents.";
    }

    if (error.status === 404) {
      return "The document no longer exists.";
    }

    if (error.status === 409) {
      return error.detail || "The document is not ready for this action.";
    }

    if (error.status === 429) {
      return "Too many requests. Please wait a moment and try again.";
    }

    if (error.status === 503) {
      return (
        error.detail ||
        "The document service is temporarily unavailable. Please try again."
      );
    }

    return error.detail;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return action === "reindex"
    ? "Unable to reindex the document."
    : "Unable to delete the document.";
}

export default function DashboardPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [user, setUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<number[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");

  const [busyDocumentId, setBusyDocumentId] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  const departmentNameById = useMemo(
    () =>
      new Map(
        departments.map((department) => [department.id, department.name]),
      ),
    [departments],
  );

  const loadDashboard = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const currentUser = await getCurrentUser();
      const documentResponse = await listDocuments(20, 0);

      setUser(currentUser);
      setDocuments(documentResponse.items);
      setTotal(documentResponse.total);

      if (currentUser.role === "admin") {
        const departmentResponse = await getDocumentDepartments();
        setDepartments(departmentResponse);
      } else {
        setDepartments([]);
      }
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }

      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load the workspace.",
      );
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadDashboard();
    }, 0);

    return () => window.clearTimeout(task);
  }, [loadDashboard]);

  function resetUploadForm() {
    setSelectedFile(null);
    setSelectedDepartmentIds([]);
    setUploadError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setUploadError("");
    setUploadSuccess("");

    if (!file) {
      setSelectedFile(null);
      return;
    }

    const extension = fileExtension(file.name);

    if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(extension)) {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setUploadError("Only PDF, TXT, and DOCX files are supported.");
      return;
    }

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setUploadError("The selected file exceeds the 20 MB frontend limit.");
      return;
    }

    setSelectedFile(file);
  }

  function toggleDepartment(departmentId: number) {
    setSelectedDepartmentIds((current) =>
      current.includes(departmentId)
        ? current.filter((id) => id !== departmentId)
        : [...current, departmentId],
    );
    setUploadError("");
    setUploadSuccess("");
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError("");
    setUploadSuccess("");

    if (!selectedFile) {
      setUploadError("Choose a document before uploading.");
      return;
    }

    if (selectedDepartmentIds.length === 0) {
      setUploadError("Select at least one department for this document.");
      return;
    }

    setUploading(true);

    try {
      const uploadedDocument = await uploadDocument(
        selectedFile,
        selectedDepartmentIds,
      );

      setUploadSuccess(
        `${uploadedDocument.filename} uploaded successfully. It is now ${uploadedDocument.status}.`,
      );
      resetUploadForm();
      await loadDashboard();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }

      setUploadError(uploadErrorMessage(requestError));
    } finally {
      setUploading(false);
    }
  }

  async function handleReindex(document: Document) {
    if (
      !window.confirm(
        `Reindex "${document.filename}"?\n\nThis will enqueue the document for ingestion again.`,
      )
    ) {
      return;
    }

    setBusyDocumentId(document.id);
    setActionError("");
    setActionSuccess("");

    try {
      const updatedDocument = await reindexDocument(document.id);

      setActionSuccess(
        `${updatedDocument.filename} reindex requested successfully. Current status: ${updatedDocument.status}.`,
      );
      await loadDashboard();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }

      setActionError(actionErrorMessage("reindex", requestError));
    } finally {
      setBusyDocumentId(null);
    }
  }

  async function handleDelete(document: Document) {
    if (
      !window.confirm(
        `Delete "${document.filename}"?\n\nThis action cannot be undone from the dashboard.`,
      )
    ) {
      return;
    }

    setBusyDocumentId(document.id);
    setActionError("");
    setActionSuccess("");

    try {
      await deleteDocument(document.id);

      setActionSuccess(
        `${document.filename} deletion requested successfully.`,
      );
      await loadDashboard();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        router.replace("/login");
        return;
      }

      setActionError(actionErrorMessage("delete", requestError));
    } finally {
      setBusyDocumentId(null);
    }
  }

  function renderDepartments(document: Document): string {
    if (document.department_ids.length === 0) {
      return "—";
    }

    return document.department_ids
      .map(
        (departmentId) =>
          departmentNameById.get(departmentId) ?? `Dept #${departmentId}`,
      )
      .join(", ");
  }

  return (
    <div className="content-stack">
      <section className="hero-panel">
        <div>
          <div className="eyebrow">AUTHORIZED KNOWLEDGE ACCESS</div>
          <h2>
            {user ? `Welcome back, ${user.email.split("@")[0]}.` : "Welcome."}
          </h2>
          <p>
            Documents shown here are returned by the backend according to your
            account authorization.
          </p>
        </div>

        <div className="hero-security">
          <span className="security-check">✓</span>
          <div>
            <strong>Authorization-first</strong>
            <span>Server-side access control</span>
          </div>
        </div>
      </section>

      <section className="stats-grid">
        <article className="stat-card">
          <span className="stat-label">Visible documents</span>
          <strong>{loading ? "—" : total}</strong>
          <span className="stat-caption">Available to this account</span>
        </article>

        <article className="stat-card">
          <span className="stat-label">Role</span>
          <strong>{user?.role ?? "—"}</strong>
          <span className="stat-caption">Resolved from /auth/me</span>
        </article>

        <article className="stat-card">
          <span className="stat-label">Department</span>
          <strong>{user?.department_id ?? "—"}</strong>
          <span className="stat-caption">
            Authorized department assignment
          </span>
        </article>
      </section>

      {user?.role === "admin" ? (
        <section className="panel upload-panel">
          <div className="panel-header">
            <div>
              <div className="eyebrow">ADMIN UPLOAD</div>
              <h3>Add knowledge to the workspace</h3>
            </div>
            <span className="badge badge-success">Admin only</span>
          </div>

          <form className="upload-form" onSubmit={handleUpload}>
            <label className="field">
              <span>Document file</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.docx"
                onChange={handleFileChange}
                disabled={uploading}
              />
            </label>

            <div className="upload-file-note">
              <span>Supported: PDF, TXT, DOCX</span>
              <span>Frontend limit: 20 MB</span>
              {selectedFile ? <strong>{selectedFile.name}</strong> : null}
            </div>

            <fieldset className="department-picker">
              <legend>Departments with access</legend>
              {departments.length === 0 ? (
                <div className="department-empty">
                  No departments are available for assignment.
                </div>
              ) : (
                <div className="department-options">
                  {departments.map((department) => {
                    const checked = selectedDepartmentIds.includes(department.id);

                    return (
                      <label
                        className={`department-option${
                          checked ? " department-option-selected" : ""
                        }`}
                        key={department.id}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleDepartment(department.id)}
                          disabled={uploading}
                        />
                        <span>
                          <strong>{department.name}</strong>
                          <small>Department #{department.id}</small>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </fieldset>

            {uploadError ? (
              <div className="page-alert page-alert-error" role="alert">
                <strong>Upload failed.</strong> {uploadError}
              </div>
            ) : null}

            {uploadSuccess ? (
              <div className="page-alert page-alert-success" role="status">
                {uploadSuccess}
              </div>
            ) : null}

            <div className="upload-actions">
              <button
                className="button button-primary"
                type="submit"
                disabled={
                  uploading ||
                  !selectedFile ||
                  selectedDepartmentIds.length === 0 ||
                  departments.length === 0
                }
              >
                {uploading ? "Uploading…" : "Upload document"}
              </button>
              <button
                className="button button-secondary"
                type="button"
                onClick={resetUploadForm}
                disabled={uploading}
              >
                Clear
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="panel">
        <div className="panel-header">
          <div>
            <div className="eyebrow">DOCUMENTS</div>
            <h3>Accessible knowledge</h3>
          </div>

          <button
            className="button button-secondary"
            type="button"
            onClick={() => void loadDashboard()}
            disabled={loading || uploading || busyDocumentId !== null}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {error ? (
          <div className="page-alert page-alert-error" role="alert">
            {error}
          </div>
        ) : null}

        {actionError ? (
          <div className="page-alert page-alert-error" role="alert">
            <strong>Document action failed.</strong> {actionError}
          </div>
        ) : null}

        {actionSuccess ? (
          <div className="page-alert page-alert-success" role="status">
            {actionSuccess}
          </div>
        ) : null}

        {loading ? (
          <div className="empty-state">
            <div className="spinner" aria-hidden="true" />
            <p>Loading authorized documents…</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">—</div>
            <h4>No documents available</h4>
            <p>
              The API returned no documents that this account is authorized to
              access.
            </p>
          </div>
        ) : (
          <div className="document-table-wrap">
            <table className="document-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Departments</th>
                  <th>Created</th>
                  {user?.role === "admin" ? <th>Actions</th> : null}
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => {
                  const isBusy = busyDocumentId === document.id;
                  const hasBusyDocument =
                    busyDocumentId !== null && busyDocumentId !== document.id;

                  return (
                    <tr key={document.id}>
                      <td>
                        <div className="document-name">{document.filename}</div>
                        <div className="document-id">
                          Document #{document.id}
                        </div>
                      </td>
                      <td>
                        <span className={statusClass(document.status)}>
                          {document.status}
                        </span>
                      </td>
                      <td>{renderDepartments(document)}</td>
                      <td>{formatDate(document.created_at)}</td>
                      {user?.role === "admin" ? (
                        <td>
                          <div className="document-actions">
                            <button
                              className="button button-small button-secondary"
                              type="button"
                              onClick={() => void handleReindex(document)}
                              disabled={
                                isBusy ||
                                hasBusyDocument ||
                                loading ||
                                uploading ||
                                document.status.toLowerCase() === "deleting"
                              }
                            >
                              {isBusy ? "Working…" : "Reindex"}
                            </button>
                            <button
                              className="button button-small button-danger"
                              type="button"
                              onClick={() => void handleDelete(document)}
                              disabled={
                                isBusy ||
                                hasBusyDocument ||
                                loading ||
                                uploading ||
                                document.status.toLowerCase() === "deleting"
                              }
                            >
                              {isBusy ? "Working…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="info-grid">
        <article className="panel info-card">
          <div className="eyebrow">NEXT</div>
          <h3>Ask RAG</h3>
          <p>
            Query the knowledge base through the existing authorization-first
            retrieval and generation pipeline.
          </p>
          <button
            className="button button-primary"
            type="button"
            onClick={() => router.push("/dashboard/query")}
          >
            Open query workspace
          </button>
        </article>

        {user?.role === "admin" ? (
          <article className="panel info-card">
            <div className="eyebrow">ADMIN</div>
            <h3>Administration</h3>
            <p>
              Manage departments and users from the administrator workspace.
            </p>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => router.push("/dashboard/admin")}
            >
              Open administration
            </button>
          </article>
        ) : (
          <article className="panel info-card">
            <div className="eyebrow">SECURITY</div>
            <h3>Your access boundary</h3>
            <p>
              The client does not decide which departments or documents you can
              access. The API remains the source of truth.
            </p>
          </article>
        )}
      </section>
    </div>
  );
}
