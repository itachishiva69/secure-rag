const TOKEN_KEY = "secure-rag.access-token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  window.sessionStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}
