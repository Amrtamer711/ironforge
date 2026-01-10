import { apiRequest } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  // endpoint used in your old chat.js
  return apiRequest("/api/sales/files/upload", { method: "POST", body: formData });
}

// old chat.js had multiple url cases; keep the same resolution logic
export function resolveFileUrl(file) {
  const base = runtimeConfig.API_BASE_URL || "";

  if (file?.preview_url) {
    return file.preview_url;
  }

  if (file?.file_url) {
    // signed supabase URLs can be used directly
    if (file.file_url.startsWith("http")) return file.file_url;

    // legacy "/api/files/..." -> proxy through /api/sales/files/
    if (file.file_url.startsWith("/api/files/")) {
      return `${base}/api/sales/files/${file.file_url.replace("/api/files/", "")}`;
    }

    // fallback (same-origin)
    return `${base}${file.file_url}`;
  }

  if (file?.url) {
    if (file.url.startsWith("http")) return file.url;

    // legacy "/api/files/..." -> proxy through /api/sales/files/
    if (file.url.startsWith("/api/files/")) {
      return `${base}/api/sales/files/${file.url.replace("/api/files/", "")}`;
    }

    return `${base}${file.url}`;
  }

  if (file?.file_id) {
    return `${base}/api/sales/files/${file.file_id}/${encodeURIComponent(file.filename || "file")}`;
  }

  return null;
}
