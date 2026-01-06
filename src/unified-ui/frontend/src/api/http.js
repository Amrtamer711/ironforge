import { runtimeConfig } from "../lib/runtimeConfig";
import { clearAuthToken, getAuthToken, setAuthToken } from "../lib/token";
import { getSupabaseClient } from "../lib/supabaseClient";

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

  const res = await fetch(url, { ...fetchOptions, headers });

  // old behavior: auto logout on 401
  if (res.status === 401) {
    clearAuthToken();
    window.dispatchEvent(new CustomEvent("auth:logout"));
    return null;
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

  const res = await fetch(url, { ...fetchOptions, headers });

  if (res.status === 401) {
    clearAuthToken();
    window.dispatchEvent(new CustomEvent("auth:logout"));
    return null;
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
