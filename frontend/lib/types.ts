export type UserRole = "admin" | "user";

export interface User {
  id: number;
  email: string;
  role: UserRole;
  department_id: number | null;
}

export interface UserResponse {
  id: number;
  email: string;
  role: string;
  department_id: number | null;
  created_at: string;
}

export interface UserListResponse {
  items: UserResponse[];
  total: number;
  limit: number;
  offset: number;
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
  conversation_id?: number;
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
  conversation_id: number | null;
}

export interface Conversation {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  detail?: string;
}
