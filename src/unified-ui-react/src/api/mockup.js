import { apiRequest, apiBlob } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

// same endpoints as your old mockup.js
export async function getLocations() {
  return apiRequest("/api/sales/mockup/locations");
}

export async function getTemplates(location, { timeOfDay, finish, venueType, locations } = {}) {
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (finish) params.set("finish", finish);
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
  // location is path param (supports slashes like "network/type/asset"), photo is query param
  return apiRequest(`/api/sales/mockup/photo/${location}?photo_filename=${encodeURIComponent(photo)}`, {
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

// TODO : This endpoint does not exist in backend now.
export async function getHistory() {
  return apiRequest("/api/sales/mockup/history");
}

export async function getTemplatePhotoBlob(location, photo, { timeOfDay, finish } = {}) {
  if (!location || !photo) return null;
  const params = new URLSearchParams();
  params.set("photo_filename", photo);  // Required query param
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (finish) params.set("finish", finish);
  // location is path param (supports slashes like "network/type/asset"), photo is query param
  const path = `/api/sales/mockup/photo/${location}?${params.toString()}`;
  return apiBlob(path);
}

export async function getTemplatePhotoBlobUrl(location, photo, { timeOfDay, finish } = {}) {
  const blob = await getTemplatePhotoBlob(location, photo, { timeOfDay, finish });
  return blob ? URL.createObjectURL(blob) : "";
}

// === ELIGIBILITY API ===

/**
 * Get locations eligible for mockup setup (networks only, no packages).
 * Used in Setup tab for frame configuration.
 */
export async function getSetupLocations() {
  return apiRequest("/api/sales/mockup/eligibility/setup");
}

/**
 * Get locations eligible for mockup generation (networks + packages with frames).
 * Used in Generate tab for location dropdown.
 */
export async function getGenerateLocations() {
  return apiRequest("/api/sales/mockup/eligibility/generate");
}

/**
 * Get all available templates for a location.
 * If location is a package, returns templates from ALL networks in package.
 * @param {string} locationKey - Network or package key
 */
export async function getEligibleTemplates(locationKey) {
  return apiRequest(`/api/sales/mockup/eligibility/templates/${encodeURIComponent(locationKey)}`);
}

/**
 * Check if a specific location is eligible for a given mode.
 * Used for validation and user feedback (especially LLM mode).
 * @param {string} locationKey - Network or package key
 * @param {string} mode - "setup", "generate_form", or "generate_llm"
 */
export async function checkEligibility(locationKey, mode = "generate_form") {
  return apiRequest("/api/sales/mockup/eligibility/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ location_key: locationKey, mode }),
  });
}

/**
 * Expand a location (network or package) to its generation targets.
 * Returns list of networks with their storage keys.
 * @param {string} locationKey - Network or package key
 */
export async function expandLocation(locationKey) {
  return apiRequest(`/api/sales/mockup/expand/${encodeURIComponent(locationKey)}`);
}
