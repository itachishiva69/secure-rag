"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "../lib/auth";

type AuthState = "checking" | "authenticated";

export default function AuthGuard({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const router = useRouter();
  const [authState, setAuthState] = useState<AuthState>("checking");

  useEffect(() => {
    const task = window.setTimeout(() => {
      if (getAccessToken()) {
        setAuthState("authenticated");
      } else {
        router.replace("/login");
      }
    }, 0);

    return () => window.clearTimeout(task);
  }, [router]);

  if (authState !== "authenticated") {
    return (
      <div className="screen-state">
        <div className="spinner" aria-hidden="true" />
        <p>Checking your session…</p>
      </div>
    );
  }

  return <>{children}</>;
}
