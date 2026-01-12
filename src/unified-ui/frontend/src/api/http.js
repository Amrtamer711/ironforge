import { runtimeConfig } from "../lib/runtimeConfig";
import { clearAuthToken, getAuthToken, setAuthToken } from "../lib/token";
import { getSupabaseClient } from "../lib/supabaseClient";

// Flag to prevent concurrent refresh attempts
let isRefreshing = false;
let refreshPromise = null;

async function resolveAuthToken() {
  const stored = getAuthToken();
  if (stored) return stored;

  const supabase = getSupabaseClient();
  if (!supabase) return null;

  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token || null;
  if (token) setAuthToken(token);
  return token;
}

async function tryRefreshToken() {
  // Prevent concurrent refresh attempts
  if (isRefreshing) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const supabase = getSupabaseClient();
      if (!supabase) return null;

      const { data, error } = await supabase.auth.refreshSession();
      if (error || !data.session?.access_token) {
        return null;
      }

      setAuthToken(data.session.access_token);
      return data.session.access_token;
    } catch (e) {
      console.error("Token refresh failed:", e);
      return null;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function apiRequest(path, options = {}) {
  const { baseUrl, ...fetchOptions } = options;
  const url = `${baseUrl ?? runtimeConfig.API_BASE_URL}${path}`;
  const headers = new Headers(fetchOptions.headers || {});

  // Don't force JSON header for FormData
  const isFormData = fetchOptions.body instanceof FormData;
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = await resolveAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res = await fetch(url, { ...fetchOptions, headers });

  // On 401: try refresh token first, then retry request
  if (res.status === 401) {
    const newToken = await tryRefreshToken();
    if (newToken) {
      // Retry with new token
      headers.set("Authorization", `Bearer ${newToken}`);
      res = await fetch(url, { ...fetchOptions, headers });
      if (res.ok || res.status !== 401) {
        // Proceed with response handling below
      } else {
        // Still 401 after refresh - logout
        clearAuthToken();
        window.dispatchEvent(new CustomEvent("auth:logout"));
        return null;
      }
    } else {
      // Refresh failed - logout
      clearAuthToken();
      window.dispatchEvent(new CustomEvent("auth:logout"));
      return null;
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    const error = new Error(err.detail || err.error || `Request failed: ${res.status}`);
    error.status = res.status;
    error.data = err;
    throw error;
  }

  // Some endpoints return no content
  if (res.status === 204) return null;

  // If response isn't JSON
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return res;

  return res.json();
}

export async function apiBlob(path, options = {}) {
  const { baseUrl, ...fetchOptions } = options;
  const url = `${baseUrl ?? runtimeConfig.API_BASE_URL}${path}`;
  const headers = new Headers(fetchOptions.headers || {});
  const token = await resolveAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res = await fetch(url, { ...fetchOptions, headers });

  // On 401: try refresh token first, then retry request
  if (res.status === 401) {
    const newToken = await tryRefreshToken();
    if (newToken) {
      // Retry with new token
      headers.set("Authorization", `Bearer ${newToken}`);
      res = await fetch(url, { ...fetchOptions, headers });
      if (res.ok || res.status !== 401) {
        // Proceed with response handling below
      } else {
        // Still 401 after refresh - logout
        clearAuthToken();
        window.dispatchEvent(new CustomEvent("auth:logout"));
        return null;
      }
    } else {
      // Refresh failed - logout
      clearAuthToken();
      window.dispatchEvent(new CustomEvent("auth:logout"));
      return null;
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    const error = new Error(err.detail || err.error || `Request failed: ${res.status}`);
    error.status = res.status;
    error.data = err;
    throw error;
  }
  return res.blob();
}
