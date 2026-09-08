import type {
  ConversationDetail,
  ConversationListResponse,
  Conversation,
  Department,
  Document,
  DocumentListResponse,
  QueryResponse,
  QuerySource,
  TokenResponse,
  User,
  UserListResponse,
  UserResponse,
} from "./types";
import { clearAccessToken, getAccessToken } from "./auth";

const API_PREFIX = "/api/backend";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };

    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    // Fall through to a generic message.
  }

  return `Request failed with status ${response.status}`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  const token = getAccessToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;

  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `Network request failed: ${error.message}`
        : "Network request failed.",
    );
  }

  if (response.status === 401) {
    clearAccessToken();

    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("secure-rag:unauthorized"));
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
    }),
  });
}

export async function getCurrentUser(): Promise<User> {
  return request<User>("/auth/me");
}

export async function listDocuments(
  limit = 20,
  offset = 0,
): Promise<DocumentListResponse> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  return request<DocumentListResponse>(`/documents?${searchParams}`);
}

export async function getDocumentDepartments(): Promise<Department[]> {
  return request<Department[]>("/departments");
}

export async function createDepartment(name: string): Promise<Department> {
  return request<Department>("/departments/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
}

export async function updateDepartment(
  departmentId: number,
  name: string,
): Promise<Department> {
  return request<Department>(`/departments/${departmentId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
}

export async function deleteDepartment(departmentId: number): Promise<void> {
  return request<void>(`/departments/${departmentId}`, {
    method: "DELETE",
  });
}

export async function uploadDocument(
  file: File,
  departmentIds: number[],
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("department_ids", departmentIds.join(","));

  return request<Document>("/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function reindexDocument(documentId: number): Promise<Document> {
  return request<Document>(`/documents/${documentId}/reindex`, {
    method: "POST",
  });
}

export async function deleteDocument(documentId: number): Promise<void> {
  return request<void>(`/documents/${documentId}`, {
    method: "DELETE",
  });
}

export async function listUsers(
  limit = 20,
  offset = 0,
): Promise<UserListResponse> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  return request<UserListResponse>(`/users?${searchParams}`);
}

export async function createUser(
  email: string,
  password: string,
  role: string,
  departmentId: number | null,
): Promise<UserResponse> {
  return request<UserResponse>("/users/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
      role,
      department_id: departmentId,
    }),
  });
}

export async function updateUser(
  userId: number,
  payload: {
    email?: string | null;
    role?: string | null;
    department_id?: number | null;
  },
): Promise<UserResponse> {
  return request<UserResponse>(`/users/${userId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function deleteUser(userId: number): Promise<void> {
  return request<void>(`/users/${userId}`, {
    method: "DELETE",
  });
}

export async function submitQuery(
  query: string,
  limit = 5,
  conversationId?: number,
): Promise<QueryResponse> {
  return request<QueryResponse>("/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      limit,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    }),
  });
}

export async function listConversations(
  limit = 50,
  offset = 0,
): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  return request<ConversationListResponse>(
    `/conversations?${searchParams}`,
  );
}

export async function getConversation(
  conversationId: number,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${conversationId}`);
}

export async function createConversation(
  title?: string | null,
): Promise<Conversation> {
  return request<Conversation>("/conversations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: title?.trim() || null,
    }),
  });
}

export async function deleteConversation(
  conversationId: number,
): Promise<void> {
  return request<void>(`/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export interface StreamStartEvent {
  conversation_id: number | null;
  sources: QuerySource[];
}

export interface StreamDoneEvent {
  conversation_id: number | null;
  answer: string;
  sources: QuerySource[];
}

export interface StreamErrorEvent {
  code: string;
  detail: string;
}

export interface StreamHandlers {
  onStart?: (event: StreamStartEvent) => void;
  onToken?: (text: string) => void;
  onDone?: (event: StreamDoneEvent) => void;
}

function parseSseBlock(block: string): {
  event: string;
  data: unknown;
} | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return {
      event,
      data: JSON.parse(dataLines.join("\n")),
    };
  } catch {
    throw new Error("The server returned an invalid streaming event.");
  }
}

export async function streamQuery(
  query: string,
  limit = 5,
  conversationId?: number,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<StreamDoneEvent> {
  const token = getAccessToken();

  if (!token) {
    throw new ApiError(401, "Authentication required.");
  }

  let response: Response;

  try {
    response = await fetch(`${API_PREFIX}/query/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      body: JSON.stringify({
        query,
        limit,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new Error(
      error instanceof Error
        ? `Network request failed: ${error.message}`
        : "Network request failed.",
    );
  }

  if (response.status === 401) {
    clearAccessToken();

    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("secure-rag:unauthorized"));
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  if (!response.body) {
    throw new Error("The server did not provide a streaming response body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEvent: StreamDoneEvent | null = null;

  try {
    while (true) {
      const readResult = await reader.read();
      const chunk = decoder.decode(readResult.value ?? new Uint8Array(), {
        stream: !readResult.done,
      });

      buffer += chunk;

      let separatorIndex = buffer.indexOf("\n\n");

      while (separatorIndex >= 0) {
        const block = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);

        const parsed = parseSseBlock(block);

        if (parsed) {
          if (parsed.event === "start") {
            handlers.onStart?.(parsed.data as StreamStartEvent);
          } else if (parsed.event === "token") {
            const data = parsed.data as { text?: unknown };

            if (typeof data.text !== "string") {
              throw new Error("The server returned an invalid token event.");
            }

            handlers.onToken?.(data.text);
          } else if (parsed.event === "done") {
            doneEvent = parsed.data as StreamDoneEvent;
            handlers.onDone?.(doneEvent);
          } else if (parsed.event === "error") {
            const data = parsed.data as Partial<StreamErrorEvent>;

            throw new ApiError(
              502,
              typeof data.detail === "string"
                ? data.detail
                : "The query stream could not be completed.",
            );
          }
        }

        separatorIndex = buffer.indexOf("\n\n");
      }

      if (readResult.done) {
        break;
      }
    }

    const trailing = buffer.trim();

    if (trailing) {
      const parsed = parseSseBlock(trailing);

      if (parsed?.event === "done") {
        doneEvent = parsed.data as StreamDoneEvent;
        handlers.onDone?.(doneEvent);
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!doneEvent) {
    throw new Error("The query stream ended before completion.");
  }

  return doneEvent;
}
