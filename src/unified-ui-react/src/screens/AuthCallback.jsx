import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../state/auth";
import { AccessPending } from "./AccessPending";

export function AuthCallback() {
  const nav = useNavigate();
  const { authReady, session, user, pendingAccess, logout } = useAuth();

  useEffect(() => {
    // If auth system initialized and still no session -> go login
    if (authReady && !session) {
      nav("/login", { replace: true });
      return;
    }

    // If session exists and user profile is loaded -> go to app
    if (authReady && session && user) {
      const next = sessionStorage.getItem("postAuthRedirect") || "/app/chat";
      sessionStorage.removeItem("postAuthRedirect");
      nav(next, { replace: true });
    }
  }, [authReady, session, user, nav]);

  if (authReady && pendingAccess) {
    return (
      <AccessPending
        email={pendingAccess.email}
        message={pendingAccess.message}
        onSignOut={logout}
      />
    );
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="rounded-2xl bg-white/55 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10 px-5 py-4 text-sm">
        Signing you in…
      </div>
    </div>
  );
}
