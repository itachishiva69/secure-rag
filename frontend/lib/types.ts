export type UserRole = "admin" | "user";

export interface User {
  id: number;
  email: string;
  role: UserRole;
  department_id: number | null;
}

export interface TokenResponse {
  access_token: string;
}

export interface Department {
  id: number;
  name: string;
  created_at: string;
}

export interface Document {
  id: number;
  filename: string;
  storage_path: string;
  uploaded_by: number;
  status: string;
  created_at: string;
  department_ids: number[];
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}

export interface QueryRequest {
  query: string;
  limit: number;
}

export interface QuerySource {
  document_id: number;
  filename: string;
  chunk_index: number;
}

export interface QueryResponse {
  query: string;
  answer: string;
  sources: QuerySource[];
}

export interface ApiErrorBody {
  detail?: string;
}