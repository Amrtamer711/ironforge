import { apiRequest } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  // endpoint used in your old chat.js
  return apiRequest("/api/sales/files/upload", { method: "POST", body: formData });
}

// Helper to convert legacy /api/files/ paths to /api/sales/files/
function normalizeFilePath(url, base) {
  if (!url) return null;
  // Signed Supabase URLs or other absolute URLs - use directly
  if (url.startsWith("http")) return url;
  // Legacy "/api/files/..." -> proxy through /api/sales/files/
  if (url.startsWith("/api/files/")) {
    return `${base}/api/sales/files/${url.replace("/api/files/", "")}`;
  }
  // Already correct format or other relative path
  return `${base}${url}`;
}

// old chat.js had multiple url cases; keep the same resolution logic
export function resolveFileUrl(file) {
  const base = runtimeConfig.API_BASE_URL || "";

  if (file?.preview_url) {
    return normalizeFilePath(file.preview_url, base);
  }

  if (file?.file_url) {
    return normalizeFilePath(file.file_url, base);
  }

  if (file?.url) {
    return normalizeFilePath(file.url, base);
  }

  if (file?.file_id) {
    return `${base}/api/sales/files/${file.file_id}/${encodeURIComponent(file.filename || "file")}`;
  }

  return null;
}
