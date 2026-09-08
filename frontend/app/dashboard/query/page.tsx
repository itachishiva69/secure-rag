"use client";

import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  streamQuery,
} from "../../../lib/api";
import { getAccessToken } from "../../../lib/auth";
import type {
  Conversation,
  ConversationDetail,
  ConversationMessage,
  QuerySource,
} from "../../../lib/types";

const DEFAULT_LIMIT = 5;
const CONVERSATION_PAGE_SIZE = 50;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Your session has expired. Please sign in again.";
    }

    if (error.status === 429) {
      return "Query rate limit reached. Please wait a moment and try again.";
    }

    if (error.status === 502) {
      return error.detail || "The language model provider is temporarily unavailable.";
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

function formatConversationTitle(conversation: Conversation): string {
  return conversation.title?.trim() || "New conversation";
}

function formatTime(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function makeMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function buildConversationTitle(question: string): string {
  const normalized = question
    .trim()
    .replace(/\s+/g, " ")
    .replace(/[?!.]+$/g, "");

  if (!normalized) {
    return "Conversation";
  }

  const maxLength = 72;

  if (normalized.length <= maxLength) {
    return normalized;
  }

  return `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
}

export default function QueryPage() {
  const router = useRouter();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] =
    useState<ConversationDetail | null>(null);
  const [query, setQuery] = useState("");
  const [streamedAnswer, setStreamedAnswer] = useState("");
  const [streamSources, setStreamSources] = useState<QuerySource[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [creatingConversation, setCreatingConversation] = useState(false);
  const [error, setError] = useState("");

  const abortControllerRef = useRef<AbortController | null>(null);
  const activeConversationIdRef = useRef<number | null>(null);
  const streamDisplayQueueRef = useRef("");
  const streamDisplayTimerRef = useRef<number | null>(null);
  const streamDisplayWaitersRef = useRef<Array<() => void>>([]);

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);

    try {
      const response = await listConversations(
        CONVERSATION_PAGE_SIZE,
        0,
      );
      setConversations(response.items);
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
      setLoadingConversations(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    void loadConversations();
  }, [loadConversations, router]);

  async function selectConversation(conversationId: number) {
    if (streaming || loadingConversation) {
      return;
    }

    setLoadingConversation(true);
    setError("");
    setStreamedAnswer("");
    setStreamSources([]);

    try {
      const conversation = await getConversation(conversationId);

      activeConversationIdRef.current = conversation.id;
      setActiveConversation(conversation);
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
      setLoadingConversation(false);
    }
  }

  function startNewConversation() {
    if (streaming) {
      return;
    }

    setError("");
    setStreamedAnswer("");
    setStreamSources([]);
    setQuery("");

    activeConversationIdRef.current = null;
    setActiveConversation(null);
  }

  async function handleDeleteConversation(
    conversationId: number,
  ) {
    if (streaming) {
      return;
    }

    const shouldDelete = window.confirm(
      "Delete this conversation and its message history?",
    );

    if (!shouldDelete) {
      return;
    }

    setError("");

    try {
      await deleteConversation(conversationId);

      setConversations((current) =>
        current.filter((item) => item.id !== conversationId),
      );

      if (activeConversationIdRef.current === conversationId) {
        activeConversationIdRef.current = null;
        setActiveConversation(null);
        setStreamedAnswer("");
        setStreamSources([]);
      }
    } catch (requestError) {
      if (
        requestError instanceof ApiError &&
        requestError.status === 401
      ) {
        router.replace("/login");
        return;
      }

      setError(errorMessage(requestError));
    }
  }

  function resolveStreamDisplayWaiters() {
    if (streamDisplayQueueRef.current) {
      return;
    }

    const waiters = streamDisplayWaitersRef.current.splice(0);

    for (const resolve of waiters) {
      resolve();
    }
  }

  function scheduleStreamDisplay() {
    if (streamDisplayTimerRef.current !== null) {
      return;
    }

    const tick = () => {
      streamDisplayTimerRef.current = null;

      const queued = streamDisplayQueueRef.current;

      if (!queued) {
        resolveStreamDisplayWaiters();
        return;
      }

      const visibleChunk = queued.slice(0, 8);
      streamDisplayQueueRef.current = queued.slice(8);

      setStreamedAnswer((current) => current + visibleChunk);

      if (streamDisplayQueueRef.current) {
        streamDisplayTimerRef.current = window.setTimeout(tick, 24);
      } else {
        resolveStreamDisplayWaiters();
      }
    };

    streamDisplayTimerRef.current = window.setTimeout(tick, 0);
  }

  function waitForStreamDisplayDrain(): Promise<void> {
    if (!streamDisplayQueueRef.current) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      streamDisplayWaitersRef.current.push(resolve);
    });
  }

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

    let conversationId = activeConversationIdRef.current;

    if (!conversationId) {
      setCreatingConversation(true);

      try {
        const conversation = await createConversation(
          buildConversationTitle(trimmedQuery),
        );

        conversationId = conversation.id;
        activeConversationIdRef.current = conversation.id;

        setConversations((current) =>
          [
            conversation,
            ...current.filter(
              (item) => item.id !== conversation.id,
            ),
          ].sort(
            (a, b) =>
              new Date(b.updated_at).getTime() -
              new Date(a.updated_at).getTime(),
          ),
        );

        setActiveConversation({
          ...conversation,
          messages: [],
        });
      } catch (requestError) {
        if (
          requestError instanceof ApiError &&
          requestError.status === 401
        ) {
          router.replace("/login");
          return;
        }

        setError(errorMessage(requestError));
        return;
      } finally {
        setCreatingConversation(false);
      }
    }

    if (!conversationId) {
      setError("Unable to determine the active conversation.");
      return;
    }

    setStreaming(true);
    setError("");
    setStreamedAnswer("");
    setStreamSources([]);

    streamDisplayQueueRef.current = "";

    if (streamDisplayTimerRef.current !== null) {
      window.clearTimeout(streamDisplayTimerRef.current);
      streamDisplayTimerRef.current = null;
    }

    streamDisplayWaitersRef.current = [];

    const optimisticUserMessage: ConversationMessage = {
      id: Number(
        `9${Date.now()}`.slice(0, 15),
      ),
      role: "user",
      content: trimmedQuery,
      created_at: new Date().toISOString(),
    };

    setActiveConversation((current) =>
      current
        ? {
            ...current,
            messages: [...current.messages, optimisticUserMessage],
            updated_at: new Date().toISOString(),
          }
        : current,
    );

    setQuery("");

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let answer = "";
    let sources: QuerySource[] = [];

    try {
      await streamQuery(
        trimmedQuery,
        DEFAULT_LIMIT,
        conversationId,
        {
          onStart: (event) => {
            sources = event.sources;
            setStreamSources(event.sources);
          },
          onToken: (text) => {
            answer += text;
            streamDisplayQueueRef.current += text;
            scheduleStreamDisplay();
          },
          onDone: (event) => {
            answer = event.answer;
            sources = event.sources;
            setStreamSources(event.sources);
          },
        },
        controller.signal,
      );

      await waitForStreamDisplayDrain();
      setStreamedAnswer(answer);

      const refreshed = await getConversation(conversationId);

      activeConversationIdRef.current = refreshed.id;
      setActiveConversation(refreshed);
      setStreamedAnswer("");

      setConversations((current) =>
        current
          .map((item) =>
            item.id === refreshed.id
              ? {
                  ...item,
                  title: refreshed.title,
                  updated_at: refreshed.updated_at,
                }
              : item,
          )
          .sort(
            (a, b) =>
              new Date(b.updated_at).getTime() -
              new Date(a.updated_at).getTime(),
          ),
      );

      if (sources.length === 0 && answer.trim()) {
        setStreamSources([]);
      }
    } catch (requestError) {
      if (
        requestError instanceof DOMException &&
        requestError.name === "AbortError"
      ) {
        setError("The response stream was cancelled.");
      } else if (
        requestError instanceof ApiError &&
        requestError.status === 401
      ) {
        router.replace("/login");
        return;
      } else {
        setError(errorMessage(requestError));
      }
    } finally {
      if (streamDisplayTimerRef.current !== null) {
        window.clearTimeout(streamDisplayTimerRef.current);
        streamDisplayTimerRef.current = null;
      }

      streamDisplayQueueRef.current = "";

      const waiters = streamDisplayWaitersRef.current.splice(0);

      for (const resolve of waiters) {
        resolve();
      }

      abortControllerRef.current = null;
      setStreaming(false);
    }
  }

  function cancelStream() {
    abortControllerRef.current?.abort();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void runQuery();
    }
  }

  function clearActiveConversation() {
    if (streaming) {
      return;
    }

    activeConversationIdRef.current = null;
    setActiveConversation(null);
    setStreamedAnswer("");
    setStreamSources([]);
    setQuery("");
    setError("");
  }

  const messages = activeConversation?.messages ?? [];

  return (
    <div className="content-stack query-workspace query-page-shell">
      <section className="hero-panel query-hero">
        <div>
          <div className="eyebrow">CONVERSATIONAL RAG</div>
          <h2>Ask your knowledge base.</h2>
          <p>
            Continue a secure conversation with grounded answers from the
            departments your account is authorized to search.
          </p>
        </div>

        <div className="hero-security query-security">
          <span className="security-check">✓</span>
          <div>
            <strong>Protected query path</strong>
            <span>
              Authorization-first retrieval · streamed grounded answers
            </span>
          </div>
        </div>
      </section>

      <section className="conversation-shell">
        <aside className="panel conversation-sidebar">
          <div className="panel-header conversation-sidebar-header">
            <div>
              <div className="eyebrow">HISTORY</div>
              <h3>Conversations</h3>
            </div>

            <button
              className="button button-primary"
              type="button"
              onClick={startNewConversation}
              disabled={streaming || creatingConversation}
            >
              New
            </button>
          </div>

          {loadingConversations ? (
            <div className="conversation-empty">
              <div className="spinner" aria-hidden="true" />
              <p>Loading conversations…</p>
            </div>
          ) : conversations.length === 0 ? (
            <div className="conversation-empty">
              <div className="empty-icon">—</div>
              <h4>No conversations yet</h4>
              <p>
                Start a new conversation and ask the knowledge base a question.
              </p>
            </div>
          ) : (
            <div className="conversation-list">
              {conversations.map((conversation) => {
                const active =
                  activeConversation?.id === conversation.id;

                return (
                  <div
                    className={`conversation-list-item${
                      active ? " conversation-list-item-active" : ""
                    }`}
                    key={conversation.id}
                  >
                    <button
                      className="conversation-select"
                      type="button"
                      onClick={() => void selectConversation(conversation.id)}
                      disabled={streaming || loadingConversation}
                    >
                      <strong>
                        {formatConversationTitle(conversation)}
                      </strong>
                      <span>
                        {formatDate(conversation.updated_at)}
                      </span>
                    </button>

                    <button
                      className="conversation-delete"
                      type="button"
                      onClick={() =>
                        void handleDeleteConversation(conversation.id)
                      }
                      disabled={streaming}
                      aria-label={`Delete ${formatConversationTitle(
                        conversation,
                      )}`}
                      title="Delete conversation"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </aside>

        <section className="panel conversation-main">
          <div className="panel-header conversation-main-header">
            <div>
              <div className="eyebrow">CHAT</div>
              <h3>
                {activeConversation
                  ? formatConversationTitle(activeConversation)
                  : "Start a conversation"}
              </h3>
            </div>

            {activeConversation ? (
              <button
                className="button button-secondary"
                type="button"
                onClick={clearActiveConversation}
                disabled={streaming}
              >
                Close
              </button>
            ) : null}
          </div>

          {loadingConversation ? (
            <div className="conversation-loading" aria-live="polite">
              <div className="spinner" aria-hidden="true" />
              <span>Loading conversation history…</span>
            </div>
          ) : null}

          {!loadingConversation && messages.length === 0 && !streamedAnswer ? (
            <div className="conversation-welcome">
              <div className="eyebrow">GROUNDED CHAT</div>
              <h4>
                Ask a question, then continue with follow-ups.
              </h4>
              <p>
                Your follow-up questions remain attached to this conversation,
                while retrieved document context continues to come from the
                authorization-first backend.
              </p>
            </div>
          ) : null}

          <div
            className="conversation-messages"
            aria-live="polite"
            aria-atomic="false"
          >
            {messages.map((message) => (
              <div
                className={`conversation-message conversation-message-${message.role}`}
                key={message.id}
              >
                <div className="conversation-message-meta">
                  <span>
                    {message.role === "user" ? "You" : "Secure RAG"}
                  </span>
                  <time dateTime={message.created_at}>
                    {formatTime(message.created_at)}
                  </time>
                </div>
                <div className="conversation-message-content">
                  {message.content}
                </div>
              </div>
            ))}

            {streaming ? (
              <div className="conversation-message conversation-message-assistant">
                <div className="conversation-message-meta">
                  <span>Secure RAG</span>
                  <span className="streaming-indicator">
                    <span className="button-spinner" aria-hidden="true" />
                    Generating
                  </span>
                </div>
                <div className="conversation-message-content">
                  {streamedAnswer || "Searching authorized knowledge…"}
                  <span className="streaming-cursor" aria-hidden="true" />
                </div>
              </div>
            ) : null}
          </div>

          {streamSources.length > 0 ? (
            <aside className="conversation-sources">
              <div className="conversation-sources-header">
                <div>
                  <div className="eyebrow">SOURCES</div>
                  <strong>Retrieved documents</strong>
                </div>
                <span className="source-count">{streamSources.length}</span>
              </div>

              <div className="source-list source-list-enhanced">
                {streamSources.map((source, index) => (
                  <div
                    className="source-card"
                    key={`${source.document_id}-${source.chunk_index}-${index}`}
                  >
                    <div className="source-rank">{index + 1}</div>
                    <div className="source-body">
                      <div className="source-filename">
                        {source.filename}
                      </div>
                      <div className="source-meta">
                        Document #{source.document_id} · Chunk{" "}
                        {source.chunk_index}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          ) : null}

          <div className="conversation-composer">
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
                placeholder={
                  activeConversation
                    ? "Ask a follow-up question…"
                    : "Example: What is our company finance policy?"
                }
                rows={4}
                maxLength={4000}
                disabled={streaming || loadingConversation}
                autoFocus
              />

              <div className="query-form-footer query-composer-footer">
                <span className="query-help">
                  Ctrl+Enter or ⌘+Enter to submit · {query.length}/4000
                </span>

                {streaming ? (
                  <button
                    className="button button-secondary"
                    type="button"
                    onClick={cancelStream}
                  >
                    Stop
                  </button>
                ) : (
                  <button
                    className="button button-primary query-submit"
                    type="submit"
                    disabled={!query.trim() || loadingConversation}
                  >
                    {activeConversation
                      ? "Send message"
                      : "Start chat"}
                  </button>
                )}
              </div>
            </form>

            {error ? (
              <div
                className="page-alert page-alert-error query-alert"
                role="alert"
              >
                <strong>Request failed.</strong>
                <span>{error}</span>
              </div>
            ) : null}
          </div>
        </section>
      </section>

      {!activeConversation && !streaming ? (
        <section className="info-grid query-info-grid">
          <article className="panel info-card">
            <div className="eyebrow">CONTEXT</div>
            <h3>Follow-ups stay together</h3>
            <p>
              Each conversation keeps its message history so later questions
              can use the conversational context without exposing prior data
              across users.
            </p>
          </article>

          <article className="panel info-card">
            <div className="eyebrow">STREAMING</div>
            <h3>Answers arrive live</h3>
            <p>
              The response appears token by token while the backend completes
              retrieval, generation, and final conversation persistence.
            </p>
          </article>

          <article className="panel info-card">
            <div className="eyebrow">SECURITY</div>
            <h3>Authorization remains server-side</h3>
            <p>
              The frontend renders conversation state and retrieved sources;
              the backend remains responsible for department and document
              authorization.
            </p>
          </article>
        </section>
      ) : null}
    </div>
  );
}
