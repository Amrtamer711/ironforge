import { apiRequest, apiBlob } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

// same endpoints as your old mockup.js
export async function getLocations() {
  return apiRequest("/api/sales/mockup/locations");
}

export async function getTemplates(location, { timeOfDay, finish } = {}) {
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (finish) params.set("finish", finish);
  return apiRequest(`/api/sales/mockup/templates/${encodeURIComponent(location)}?${params.toString()}`);
}

export async function saveSetupPhoto(formData) {
  //return apiRequest("/api/sales/mockup/setup/save", { method: "POST", body: formData });
  return apiRequest("/api/sales/mockup/save-frame", { method: "POST", body: formData });
}

export async function deleteSetupPhoto(location, photo) {
  return apiRequest(`/api/sales/mockup/setup/delete/${encodeURIComponent(location)}/${encodeURIComponent(photo)}`, {
    method: "DELETE",
  });
}

export async function testPreview(formData) {
  return apiBlob("/api/sales/mockup/test-preview", { method: "POST", body: formData });
}

export async function generateMockup(formData) {
  // returns image blob like old mockup.js
  return apiBlob("/api/sales/mockup/generate", { method: "POST", body: formData });
}

export function getTemplatePhotoUrl(location, photo) {
  if (!location || !photo) return "";
  return `${runtimeConfig.API_BASE_URL}/api/sales/mockup/photo/${encodeURIComponent(location)}/${encodeURIComponent(photo)}`;
}

// TODO : This endpoint does not exist in backend now.
export async function getHistory() {
  return apiRequest("/api/sales/mockup/history");
}

export async function getTemplatePhotoBlob(location, photo, { timeOfDay, finish } = {}) {
  if (!location || !photo) return null;
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (finish) params.set("finish", finish);
  const query = params.toString();
  const path = `/api/sales/mockup/photo/${encodeURIComponent(location)}/${encodeURIComponent(photo)}${query ? `?${query}` : ""}`;
  return apiBlob(path);
}

export async function getTemplatePhotoBlobUrl(location, photo, { timeOfDay, finish } = {}) {
  const blob = await getTemplatePhotoBlob(location, photo, { timeOfDay, finish });
  return blob ? URL.createObjectURL(blob) : "";
}
