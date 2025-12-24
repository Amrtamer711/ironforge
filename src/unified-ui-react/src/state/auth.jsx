import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getSupabaseClient } from "../lib/supabaseClient";
import { clearAuthToken, setAuthToken } from "../lib/token";
import { apiRequest } from "../api/http";

const AuthContext = createContext(null);
const profileToRoles = {
  system_admin: ["admin", "hos", "sales_person"],
  sales_manager: ["hos", "sales_person"],
  sales_user: ["sales_person"],
  coordinator: ["coordinator"],
  finance: ["finance"],
  viewer: ["viewer"],
};

const devUsers = {
  "admin@mmg.com": {
    password: "admin123",
    id: "dev-admin-1",
    name: "Sales Admin",
    email: "admin@mmg.com",
    roles: ["admin", "hos", "sales_person"],
  },
  "hos@mmg.com": {
    password: "hos123",
    id: "dev-hos-1",
    name: "Head of Sales",
    email: "hos@mmg.com",
    roles: ["hos", "sales_person"],
  },
  "sales@mmg.com": {
    password: "sales123",
    id: "dev-sales-1",
    name: "Sales Person",
    email: "sales@mmg.com",
    roles: ["sales_person"],
  },
};

function uniqLower(arr) {
  return Array.from(new Set((arr || []).filter(Boolean).map((s) => String(s).toLowerCase())));
}

function normalizePermissions(perms = []) {
  return perms.map((p) => String(p || "").replaceAll(".", ":"));
}

function normalizeProfileName(name) {
  return (name || "sales_user").toLowerCase();
}

function buildNameFromSession(sessionUser, profileName) {
  return (
    sessionUser?.user_metadata?.full_name ||
    sessionUser?.user_metadata?.name ||
    sessionUser?.identities?.[0]?.identity_data?.full_name ||
    sessionUser?.identities?.[0]?.identity_data?.name ||
    sessionUser?.email?.split("@")[0] ||
    profileName ||
    "User"
  );
}

export function hasPermission(user, required) {
  const perms = user?.permissions || [];
  if (!perms.length) return false;

  // normalize separator: allow "*.*.*" or "*:*:*"
  const norm = (s) => String(s || "").trim().replaceAll(".", ":");

  const normalizedPerms = perms.map(norm);
  const normalizedRequired = norm(required);

  // global superuser
  if (normalizedPerms.includes("*:*:*")) return true;

  const [rm, rr, ra] = normalizedRequired.split(":");

  return normalizedPerms.some((p) => {
    const [pm, pr, pa] = p.split(":");

    // exact
    if (p === normalizedRequired) return true;

    // wildcard matching
    const mOk = pm === "*" || pm === rm;
    const rOk = pr === "*" || pr === rr;
    const aOk = pa === "*" || pa === ra || pa === "manage";

    return mOk && rOk && aOk;
  });
}

export function hasAnyPermission(user, permissions = []) {
  return permissions.some((perm) => hasPermission(user, perm));
}

export function hasAllPermissions(user, permissions = []) {
  return permissions.every((perm) => hasPermission(user, perm));
}

export function canAccessAdmin(user) {
  return (
    user?.roles?.includes("admin") ||
    user?.profile?.toLowerCase?.() === "system_admin" ||
    hasPermission(user, "*:*:*") ||         
    hasPermission(user, "core:*:*") ||
    hasPermission(user, "core:system:admin")
  );
}

export function AuthProvider({ children }) {
  const supabase = getSupabaseClient();
  const isLocalDev = !supabase && window.location.hostname === "localhost";

  const [session, setSession] = useState(null);
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("mmg_user") || localStorage.getItem("userData");
    return raw ? JSON.parse(raw) : null;
  });
  const [authReady, setAuthReady] = useState(false);
  const [pendingAccess, setPendingAccess] = useState(null);

  // Handle Supabase OAuth hash errors (otp_expired/access_denied, etc.)
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash || !hash.includes("error=")) return;

    const params = new URLSearchParams(hash.substring(1));
    const error = params.get("error");
    const errorCode = params.get("error_code");
    const errorDescription = params.get("error_description");

    if (error) {
      let userMessage = errorDescription ? decodeURIComponent(errorDescription.replace(/\+/g, " ")) : "Authentication failed";
      if (errorCode === "otp_expired") {
        userMessage = "Email link has expired. Please sign up again to receive a new confirmation email.";
      } else if (errorCode === "access_denied") {
        userMessage = "Access denied. The link may have expired or already been used.";
      }
      setTimeout(() => alert(userMessage), 300);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }, []);

  // Mirrors old behavior: on returning from OAuth, supabase session becomes available.
  useEffect(() => {
    let unsub = null;

    async function init() {
      try {
        if (!supabase) {
          // Dev/backend-only mode
          const stored = localStorage.getItem("mmg_user") || localStorage.getItem("userData");
          if (stored) setUser(JSON.parse(stored));
          setAuthReady(true);
          return;
        }

        const { data } = await supabase.auth.getSession();
        const s = data?.session || null;

        setSession(s || null);
        if (!s) {
          clearAuthToken();
          setUser(null);
          localStorage.removeItem("mmg_user");
          localStorage.removeItem("userData");
        }
        if (s?.access_token) setAuthToken(s.access_token);

        // Always refresh RBAC profile from backend
        if (s?.access_token) {
          await refreshProfile(s.access_token, s.user);
        }

        unsub = supabase.auth.onAuthStateChange(async (_event, newSession) => {
          setSession(newSession || null);

          if (newSession?.access_token) {
            setAuthToken(newSession.access_token);
            if (!pendingAccess) {
              await refreshProfile(newSession.access_token, newSession.user);
            }
          } else {
            clearAuthToken();
            setUser(null);
            localStorage.removeItem("mmg_user");
            localStorage.removeItem("userData");
          }
        }).data.subscription;

        setAuthReady(true);
      } catch {
        setAuthReady(true);
      }
    }

    init();
    return () => unsub?.unsubscribe?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supabase, pendingAccess]);

  // Old project behavior: 401 triggers event logout
  useEffect(() => {
    const onLogout = () => {
      setPendingAccess(null);
      logout();
    };
    window.addEventListener("auth:logout", onLogout);
    return () => window.removeEventListener("auth:logout", onLogout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshProfile(accessToken, sessionUser = null) {
    // Source of truth for roles/permissions (same endpoint as old auth.js)
    try {
      const profile = await apiRequest("/api/base/auth/me", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!profile) {
        return null;
      }

      const profileName = normalizeProfileName(
        profile?.profile_name || profile?.profile || profile?.profileName
      );

      const rolesFromProfile = profileToRoles[profileName] || ["sales_person"];
      const rolesFromServer =
        profile?.roles || profile?.rbac_roles || profile?.user_roles || [];

      const normalized = {
        id: profile?.id || sessionUser?.id,
        email: profile?.email || sessionUser?.email,
        name: profile?.name || buildNameFromSession(sessionUser, profileName),
        profile: profileName,
        profile_name: profileName,
        roles: uniqLower([...rolesFromProfile, ...rolesFromServer]),
        permissions: normalizePermissions(profile?.permissions || []),
        raw: profile,
      };

      setUser(normalized);
      localStorage.setItem("mmg_user", JSON.stringify(normalized));
      localStorage.setItem("userData", JSON.stringify(normalized));
      setPendingAccess(null);
      return normalized;
    } catch (error) {
      if (error?.status === 403 && error?.data?.requiresLogout) {
        const email = sessionUser?.email || user?.email || "";
        if (error?.data?.code === "USER_PENDING_APPROVAL") {
          setPendingAccess({
            pending: true,
            email,
            message: error?.data?.error || "Your account is pending administrator approval.",
          });
          return null;
        }
        await logout();
        return null;
      }

      // Fallback to session user metadata if backend not reachable
      if (sessionUser) {
        const profileName = sessionUser.user_metadata?.profile || "sales_user";
        const rolesFromProfile = profileToRoles[profileName] || ["sales_person"];
        const fallbackUser = {
          id: sessionUser.id,
          email: sessionUser.email,
          name: buildNameFromSession(sessionUser, profileName),
          profile: profileName,
          profile_name: profileName,
          roles: uniqLower(rolesFromProfile),
          permissions: [],
          raw: sessionUser,
        };
        setUser(fallbackUser);
        localStorage.setItem("mmg_user", JSON.stringify(fallbackUser));
        localStorage.setItem("userData", JSON.stringify(fallbackUser));
        setPendingAccess(null);
        return fallbackUser;
      }
      return null;
    }
  }

  async function getAccessToken() {
    // Prefer live session token; fallback to localStorage (compat w old modules)
    if (session?.access_token) return session.access_token;
    return localStorage.getItem("authToken");
  }

  // Dev/local email-password (same behavior as old auth.js when no Supabase)
  async function signInWithPassword({ email, password }) {
    setPendingAccess(null);

    if (!supabase) {
      if (!isLocalDev) {
        throw new Error("Supabase not configured");
      }
      const devUser = devUsers[email.toLowerCase()];
      if (!devUser || devUser.password !== password) {
        throw new Error("Invalid email or password");
      }

      const profileName = devUser.profile || (devUser.roles?.includes("admin") ? "system_admin" : "sales_user");
      const roles = uniqLower(devUser.roles || profileToRoles[profileName] || ["sales_person"]);
      const devUserObj = {
        id: devUser.id,
        email: devUser.email,
        name: devUser.name,
        profile: profileName,
        profile_name: profileName,
        roles,
        permissions: normalizePermissions(devUser.permissions || []),
        raw: devUser,
      };

      const token = `dev-token-${Date.now()}`;
      setAuthToken(token);
      setUser(devUserObj);
      localStorage.setItem("mmg_user", JSON.stringify(devUserObj));
      localStorage.setItem("userData", JSON.stringify(devUserObj));
      return devUserObj;
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;

    setAuthToken(data.session.access_token);
    await refreshProfile(data.session.access_token, data.session.user);
    return data;
  }

  // Microsoft SSO (same provider as old auth.js)
  async function signInWithMicrosoft() {
    if (!supabase) throw new Error("Supabase not configured. Please contact your administrator.");
    const redirectTo = getAuthRedirectUrl();

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "azure",
      options: {
        scopes: "email profile openid",
        redirectTo,
      },
    });
    if (error) throw error;
    return data; // redirect happens
  }

  // Invite-token signup flow (same endpoints as old auth.js)
  async function signUpWithInvite({ token, email, password, fullName }) {
    if (!supabase) throw new Error("Supabase not configured");

    // 1) validate invite (doesn't consume)
    const tokenData = await apiRequest("/api/base/auth/validate-invite", {
      method: "POST",
      body: JSON.stringify({ token, email }),
    });

    // 2) create supabase user
    const { data: signupData, error: signupError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName, profile: tokenData?.profile_name || "sales_user" } },
    });
    if (signupError) throw signupError;

    // 3) consume invite (backend links to RBAC profile)
    await apiRequest("/api/base/auth/consume-invite", {
      method: "POST",
      body: JSON.stringify({
        token,
        email,
        supabase_user_id: signupData?.user?.id,
        profile_name: tokenData?.profile_name,
        name: fullName,
      }),
    });

    return signupData;
  }

  async function logout() {
    try {
      if (supabase) await supabase.auth.signOut();
    } finally {
      clearAuthToken();
      setSession(null);
      setUser(null);
      setPendingAccess(null);
      localStorage.removeItem("mmg_user");
      localStorage.removeItem("userData");
      sessionStorage.removeItem("msSsoPending");
    }
  }

  const value = useMemo(
    () => ({
      authReady,
      user,
      session,
      pendingAccess,
      getAccessToken,
      signInWithPassword,
      signInWithMicrosoft,
      signUpWithInvite,
      refreshProfile,
      logout,
    }),
    [authReady, user, session, pendingAccess]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function hasRole(user, role) {
  const roles = user?.roles || [];
  return roles.includes(role) || roles.includes(role?.toLowerCase?.());
}

function getAuthRedirectUrl() {
  const localOrigin = `${window.location.protocol}//${window.location.host}`;
  const override =
    window.SUPABASE_REDIRECT_URL || import.meta.env.VITE_SUPABASE_REDIRECT_URL || "";

  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return `${localOrigin}/auth/callback`;
  }

  const base = override || localOrigin;
  return `${base.replace(/\/$/, "")}/auth/callback`;
}
