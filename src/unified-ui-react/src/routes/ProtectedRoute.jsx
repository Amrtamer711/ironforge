import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../state/auth";
import { AccessPending } from "../screens/AccessPending";

export function ProtectedRoute({ children }) {
  const { user, authReady, session, pendingAccess, logout } = useAuth();
  const loc = useLocation();

  // Wait for Supabase session + backend profile
  if (!authReady) {
    return (
      <div className="min-h-screen grid place-items-center px-4">
        <div className="rounded-2xl bg-white/55 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10 px-5 py-4 text-sm">
          Loading…
        </div>
      </div>
    );
  }

  if (pendingAccess) {
    return (
      <AccessPending
        email={pendingAccess.email}
        message={pendingAccess.message}
        onSignOut={logout}
      />
    );
  }

  // Session exists but user not yet loaded from /api/base/auth/me
  if (session && !user) {
    return (
      <div className="min-h-screen grid place-items-center px-4">
        <div className="rounded-2xl bg-white/55 dark:bg-white/5 backdrop-blur-md shadow-soft ring-1 ring-black/5 dark:ring-white/10 px-5 py-4 text-sm">
          Finalizing sign-in…
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }

  return children;
}
