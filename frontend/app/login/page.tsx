"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getCurrentUser, login } from "../../lib/api";
import { getAccessToken, setAccessToken } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      return;
    }

    getCurrentUser()
      .then(() => router.replace("/dashboard"))
      .catch(() => {
        // An invalid token will simply leave the user on the login page.
      });
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      const tokenResponse = await login(email.trim(), password);
      setAccessToken(tokenResponse.access_token);

      // Validate the token immediately so the UI never enters a
      // partially authenticated state.
      await getCurrentUser();

      router.replace("/dashboard");
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setError(requestError.detail);
      } else {
        setError("Unable to reach the Secure RAG API.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark brand-mark-large">SR</div>
          <div>
            <div className="brand-name">Secure RAG</div>
            <div className="brand-subtitle">Department-aware knowledge access</div>
          </div>
        </div>

        <div className="auth-heading">
          <div className="eyebrow">WELCOME BACK</div>
          <h1>Sign in to your workspace</h1>
          <p>
            Access the knowledge base available to your authenticated account.
          </p>
        </div>

        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
            />
          </label>

          {error ? (
            <div className="page-alert page-alert-error" role="alert">
              {error}
            </div>
          ) : null}

          <button
            className="button button-primary button-full"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="auth-footnote">
          <span className="status-dot" />
          Authentication is handled by the existing FastAPI backend.
        </div>
      </section>
    </main>
  );
}
