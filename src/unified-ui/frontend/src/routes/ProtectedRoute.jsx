import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../state/auth";
import { AccessPending } from "../screens/AccessPending";

export function ProtectedRoute({ children }) {
  const { user, authReady, session, pendingAccess, logout } = useAuth();
  const loc = useLocation();

  // No loading screen here - let individual pages handle their own loading states
  // This prevents multiple loading spinners and improves perceived performance
  if (!authReady || (session && !user)) {
    console.log("[ProtectedRoute] Waiting for auth", { authReady, hasSession: !!session, hasUser: !!user });
    return null;
  }

  console.log("[ProtectedRoute] Auth ready, rendering children", { user: user?.email });

  if (pendingAccess) {
    return (
      <AccessPending
        email={pendingAccess.email}
        message={pendingAccess.message}
        onSignOut={logout}
      />
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }

  return children;
}
