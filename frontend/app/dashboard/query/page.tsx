"use client";

import { FormEvent, KeyboardEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, submitQuery } from "../../../lib/api";
import { getAccessToken } from "../../../lib/auth";
import type { QueryResponse } from "../../../lib/types";

const DEFAULT_LIMIT = 5;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return "Query rate limit reached. Please wait a moment and try again.";
    }

    if (error.status === 502) {
      return "The language model provider is temporarily unavailable. Please try again.";
    }

    if (error.status === 503) {
      return error.detail || "The retrieval service is temporarily unavailable.";
    }

    return error.detail;
  }

  return error instanceof Error
    ? error.message
    : "Unable to complete the query.";
}

export default function QueryPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runQuery(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    const trimmedQuery = query.trim();

    if (!trimmedQuery) {
      setError("Enter a question before searching the knowledge base.");
      return;
    }

    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await submitQuery(trimmedQuery, DEFAULT_LIMIT);
      setResult(response);
    } catch (requestError) {
      if (
        requestError instanceof ApiError &&
        requestError.status === 401
      ) {
        router.replace("/login");
        return;
      }

      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void runQuery();
    }
  }

  function clearWorkspace() {
    setQuery("");
    setResult(null);
    setError("");
  }

  return (
    <div className="content-stack query-workspace">
      <section className="hero-panel query-hero">
        <div>
          <div className="eyebrow">AUTHORIZATION-FIRST RETRIEVAL</div>
          <h2>Ask your knowledge base.</h2>
          <p>
            Ask a question in natural language. The API determines which
            departments you are allowed to search before retrieval and
            generation take place.
          </p>
        </div>

        <div className="hero-security query-security">
          <span className="security-check">✓</span>
          <div>
            <strong>Protected query path</strong>
            <span>Server-side authorization + grounded sources</span>
          </div>
        </div>
      </section>

      <section className="panel query-panel">
        <div className="panel-header">
          <div>
            <div className="eyebrow">QUESTION</div>
            <h3>What do you need to know?</h3>
          </div>

          {result ? (
            <button
              className="button button-secondary"
              type="button"
              onClick={clearWorkspace}
              disabled={loading}
            >
              New question
            </button>
          ) : null}
        </div>

        <form onSubmit={runQuery}>
          <label className="sr-only" htmlFor="rag-query">
            Ask a question
          </label>
          <textarea
            id="rag-query"
            className="query-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Example: What is our company finance policy?"
            rows={6}
            maxLength={4000}
            disabled={loading}
            autoFocus
          />

          <div className="query-form-footer">
            <span className="query-help">
              Ctrl+Enter or ⌘+Enter to submit · {query.length}/4000
            </span>
            <button
              className="button button-primary query-submit"
              type="submit"
              disabled={loading || !query.trim()}
            >
              {loading ? (
                <>
                  <span className="button-spinner" aria-hidden="true" />
                  Searching…
                </>
              ) : (
                "Ask RAG"
              )}
            </button>
          </div>
        </form>

        {error ? (
          <div className="page-alert page-alert-error query-alert" role="alert">
            <strong>Query failed.</strong>
            <span>{error}</span>
          </div>
        ) : null}
      </section>

      {loading ? (
        <section className="panel query-loading" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <div>
            <strong>Searching your authorized knowledge…</strong>
            <p>
              Retrieval, validation, reranking, and answer generation are being
              handled by the API.
            </p>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="query-results" aria-live="polite">
          <article className="panel answer-panel">
            <div className="panel-header">
              <div>
                <div className="eyebrow">ANSWER</div>
                <h3>Grounded response</h3>
              </div>
              <span className="badge badge-success">Generated</span>
            </div>

            <div className="answer-question">
              <span className="answer-question-label">You asked</span>
              <span>{result.query}</span>
            </div>

            <div className="answer-text">{result.answer}</div>
          </article>

          <aside className="panel sources-panel">
            <div className="panel-header">
              <div>
                <div className="eyebrow">SOURCES</div>
                <h3>Retrieved documents</h3>
              </div>
              <span className="source-count">{result.sources.length}</span>
            </div>

            {result.sources.length === 0 ? (
              <div className="source-empty">
                <span className="empty-icon">—</span>
                <p>
                  No source documents were returned. The API may not have found
                  relevant information within this account&apos;s authorized
                  knowledge.
                </p>
              </div>
            ) : (
              <div className="source-list">
                {result.sources.map((source, index) => (
                  <div
                    className="source-card"
                    key={`${source.document_id}-${source.chunk_index}-${index}`}
                  >
                    <div className="source-rank">{index + 1}</div>
                    <div className="source-body">
                      <div className="source-filename">{source.filename}</div>
                      <div className="source-meta">
                        Document #{source.document_id} · Chunk {source.chunk_index}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="source-security-note">
              Sources are returned by the authorization-first backend. The
              frontend does not decide which documents are eligible.
            </div>
          </aside>
        </section>
      ) : null}

      {!result && !loading ? (
        <section className="info-grid query-info-grid">
          <article className="panel info-card">
            <div className="eyebrow">RETRIEVAL</div>
            <h3>Search stays scoped</h3>
            <p>
              Your question is sent to the backend, where department access is
              resolved before vector retrieval begins.
            </p>
          </article>

          <article className="panel info-card">
            <div className="eyebrow">GROUNDING</div>
            <h3>Sources stay visible</h3>
            <p>
              Successful responses include the document and chunk references
              used to build the grounded answer.
            </p>
          </article>

          <article className="panel info-card">
            <div className="eyebrow">SECURITY</div>
            <h3>No client-side authorization</h3>
            <p>
              The browser only renders the API result. It never decides which
              department or document data can reach the model.
            </p>
          </article>
        </section>
      ) : null}
    </div>
  );
}