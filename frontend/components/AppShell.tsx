"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import AuthGuard from "./AuthGuard";
import { clearAccessToken } from "../lib/auth";
import { ApiError, getCurrentUser } from "../lib/api";
import type { User } from "../lib/types";

const navItems = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/query", label: "Ask RAG" },
];

export default function AppShell({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadUser() {
      try {
        const currentUser = await getCurrentUser();

        if (!cancelled) {
          setUser(currentUser);
          setLoadError("");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }

        setLoadError(
          error instanceof Error
            ? error.message
            : "Unable to load your account.",
        );
      } finally {
        if (!cancelled) {
          setLoadingUser(false);
        }
      }
    }

    loadUser();

    function handleUnauthorized() {
      router.replace("/login");
    }

    window.addEventListener(
      "secure-rag:unauthorized",
      handleUnauthorized,
    );

    return () => {
      cancelled = true;
      window.removeEventListener(
        "secure-rag:unauthorized",
        handleUnauthorized,
      );
    };
  }, [router]);

  function signOut() {
    clearAccessToken();
    router.replace("/login");
  }

  return (
    <AuthGuard>
      <div className="app-frame">
        <aside className="sidebar">
          <div className="brand-block">
            <div className="brand-mark">SR</div>
            <div>
              <div className="brand-name">Secure RAG</div>
              <div className="brand-subtitle">Knowledge workspace</div>
            </div>
          </div>

          <nav className="sidebar-nav" aria-label="Primary navigation">
            {navItems.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/dashboard" &&
                  pathname.startsWith(item.href));

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-link ${active ? "nav-link-active" : ""}`}
                >
                  <span>{item.label}</span>
                </Link>
              );
            })}

            {user?.role === "admin" ? (
              <Link
                href="/dashboard/admin"
                className={`nav-link ${
                  pathname.startsWith("/dashboard/admin")
                    ? "nav-link-active"
                    : ""
                }`}
              >
                <span>Administration</span>
              </Link>
            ) : null}
          </nav>

          <div className="sidebar-footer">
            <div className="security-note">
              <span className="status-dot" />
              Authorization enforced by API
            </div>

            <button
              className="button button-secondary button-full"
              type="button"
              onClick={signOut}
            >
              Sign out
            </button>
          </div>
        </aside>

        <div className="main-area">
          <header className="topbar">
            <div>
              <div className="eyebrow">SECURE RAG</div>
              <h1 className="topbar-title">
                {pathname === "/dashboard"
                  ? "Workspace overview"
                  : pathname.includes("/query")
                    ? "Ask your knowledge base"
                    : "Administration"}
              </h1>
            </div>

            <div className="user-chip">
              <div className="user-avatar">
                {user?.email?.slice(0, 1).toUpperCase() ?? "?"}
              </div>
              <div>
                <div className="user-email">
                  {loadingUser ? "Loading…" : user?.email ?? "Unknown user"}
                </div>
                <div className="user-role">
                  {user?.role ?? "—"}
                  {user?.department_id !== null &&
                  user?.department_id !== undefined
                    ? ` · Department ${user.department_id}`
                    : ""}
                </div>
              </div>
            </div>
          </header>

          {loadError ? (
            <div className="page-alert page-alert-error" role="alert">
              {loadError}
            </div>
          ) : null}

          <main className="page-content">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
