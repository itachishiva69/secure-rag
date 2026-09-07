import type {
  Department,
  DocumentListResponse,
  QueryResponse,
  TokenResponse,
  User,
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
  return request<Department[]>("/departments/");
}

export async function submitQuery(
  query: string,
  limit = 5,
): Promise<QueryResponse> {
  // Use the proxy's dedicated /query rewrite so the browser never follows
  // FastAPI's /query -> /query/ redirect across origins.
  return request<QueryResponse>("/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      limit,
    }),
  });
}