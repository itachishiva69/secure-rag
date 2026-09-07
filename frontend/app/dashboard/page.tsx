"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getCurrentUser, listDocuments } from "../../lib/api";
import { getAccessToken } from "../../lib/auth";
import type { Document, User } from "../../lib/types";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusClass(status: string): string {
  switch (status) {
    case "indexed":
      return "badge badge-success";
    case "processing":
    case "uploaded":
      return "badge badge-warning";
    case "failed":
      return "badge badge-danger";
    default:
      return "badge";
  }
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const [currentUser, documentResponse] = await Promise.all([
        getCurrentUser(),
        listDocuments(20, 0),
      ]);

      setUser(currentUser);
      setDocuments(documentResponse.items);
      setTotal(documentResponse.total);
    } catch (requestError) {
      if (
        requestError instanceof ApiError &&
        requestError.status === 401
      ) {
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
    // Defer the first state update outside the synchronous effect body.
    const task = window.setTimeout(() => {
      void loadDashboard();
    }, 0);

    return () => window.clearTimeout(task);
  }, [loadDashboard]);

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
            disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {error ? (
          <div className="page-alert page-alert-error" role="alert">
            {error}
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
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
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
                    <td>
                      {document.department_ids.length > 0
                        ? document.department_ids.join(", ")
                        : "—"}
                    </td>
                    <td>{formatDate(document.created_at)}</td>
                  </tr>
                ))}
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
              Manage departments and later document ingestion from the
              administrator workspace.
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
