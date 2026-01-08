import { apiRequest, apiBlob } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

// same endpoints as your old mockup.js
export async function getLocations() {
  return apiRequest("/api/sales/mockup/locations");
}

export async function getTemplates(location, { timeOfDay, side, venueType, locations } = {}) {
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  if (venueType) params.set("venue_type", venueType);

  const locationList = Array.isArray(locations) ? locations : Array.isArray(location) ? location : [];
  if (locationList.length) {
    params.set("location_keys", JSON.stringify(locationList));
  }

  const primaryLocation = Array.isArray(location) ? location[0] : location;
  return apiRequest(`/api/sales/mockup/templates/${encodeURIComponent(primaryLocation)}?${params.toString()}`);
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
  // Returns either a Response (image blob) or JSON payload with multiple images.
  return apiRequest("/api/sales/mockup/generate", { method: "POST", body: formData });
}

export function getTemplatePhotoUrl(location, photo) {
  if (!location || !photo) return "";
  return `${runtimeConfig.API_BASE_URL}/api/sales/mockup/photo/${encodeURIComponent(location)}/${encodeURIComponent(photo)}`;
}

// TODO : This endpoint does not exist in backend now.
export async function getHistory() {
  return apiRequest("/api/sales/mockup/history");
}

export async function getTemplatePhotoBlob(location, photo, { timeOfDay, side } = {}) {
  if (!location || !photo) return null;
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  const query = params.toString();
  const path = `/api/sales/mockup/photo/${encodeURIComponent(location)}/${encodeURIComponent(photo)}${query ? `?${query}` : ""}`;
  return apiBlob(path);
}

export async function getTemplatePhotoBlobUrl(location, photo, { timeOfDay, side } = {}) {
  const blob = await getTemplatePhotoBlob(location, photo, { timeOfDay, side });
  return blob ? URL.createObjectURL(blob) : "";
}
