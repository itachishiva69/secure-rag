"use client";

import { useEffect, useState } from "react";
import { ApiError, getCurrentUser } from "../../../lib/api";
import { useRouter } from "next/navigation";
import type { User } from "../../../lib/types";

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getCurrentUser()
      .then((currentUser) => {
        if (currentUser.role !== "admin") {
          router.replace("/dashboard");
          return;
        }

        setUser(currentUser);
      })
      .catch((requestError) => {
        if (requestError instanceof ApiError && requestError.status === 401) {
          router.replace("/login");
          return;
        }

        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load your account.",
        );
      });
  }, [router]);

  return (
    <section className="panel placeholder-panel">
      <div className="eyebrow">ADMINISTRATOR</div>
      <h2>Administration workspace</h2>
      <p>
        This protected area is available only to administrator accounts. The
        full department-management and document-ingestion UI will be added in
        the next frontend milestone.
      </p>

      {user ? (
        <div className="admin-access-card">
          <span>Authenticated administrator</span>
          <strong>{user.email}</strong>
        </div>
      ) : null}

      {error ? (
        <div className="page-alert page-alert-error" role="alert">
          {error}
        </div>
      ) : null}
    </section>
  );
}
