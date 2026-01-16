import { apiRequest, apiBlob } from "./http";
import { runtimeConfig } from "../lib/runtimeConfig";

// same endpoints as your old mockup.js
export async function getLocations() {
  return apiRequest("/api/sales/mockup/locations");
}

export async function getAssetTypes() {
  return apiRequest("/api/assets/asset-types");
}

/**
 * Get asset types for a specific network by network key.
 * Returns empty array for standalone networks (no asset types).
 * @param {string} networkKey - The network key to fetch asset types for
 */
export async function getAssetTypesByNetworkKey(networkKey) {
  if (!networkKey) return [];
  return apiRequest(`/api/assets/asset-types/by-network/${encodeURIComponent(networkKey)}`);
}

export async function getTemplates(location, { timeOfDay, side, venueType } = {}) {
  const params = new URLSearchParams();
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  if (venueType) params.set("venue_type", venueType);

  const primaryLocation = Array.isArray(location) ? location[0] : location;
  if (!primaryLocation) return [];
  return apiRequest(`/api/sales/mockup/templates/${encodeURIComponent(primaryLocation)}?${params.toString()}`);
}

export async function saveSetupPhoto(formData) {
  //return apiRequest("/api/sales/mockup/setup/save", { method: "POST", body: formData });
  return apiRequest("/api/sales/mockup/save-frame", { method: "POST", body: formData });
}

/**
 * Invalidate mockup frame caches.
 * Call after save/update/delete operations to ensure fresh data.
 * @param {string} locationKey - Optional location key to invalidate specific cache
 */
export async function invalidateMockupCache(locationKey) {
  const params = new URLSearchParams();
  if (locationKey) params.set("location_key", locationKey);
  return apiRequest(`/api/sales/mockup/cache/invalidate?${params.toString()}`, { method: "POST" });
}

export async function updateSetupPhoto(formData) {
  // Update an existing mockup frame in place (doesn't create new auto-numbered filename)
  return apiRequest("/api/sales/mockup/update-frame", { method: "PUT", body: formData });
}

export async function deleteSetupPhoto(location, photo, { timeOfDay, side } = {}) {
  // location is path param (supports slashes like "network/type/asset"), photo is query param
  const params = new URLSearchParams();
  params.set("photo_filename", photo);
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  return apiRequest(`/api/sales/mockup/photo/${location}?${params.toString()}`, {
    method: "DELETE",
  });
}

export async function getMockupFrameFromAssets({
  company,
  locationKey,
  environment = "outdoor",
  timeOfDay = "day",
  side = "gold",
  photoFilename,
} = {}) {
  if (!company || !locationKey) return null;
  const params = new URLSearchParams();
  if (environment) params.set("environment", environment);
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  if (photoFilename) params.set("photo_filename", photoFilename);
  const encodedLocation = encodeURIComponent(locationKey);
  return apiRequest(`/api/assets/mockup-frames/${company}/${encodedLocation}/frame?${params.toString()}`);
}

export async function deleteMockupFrameFromAssets({
  company,
  locationKey,
  environment = "outdoor",
  timeOfDay = "day",
  side = "gold",
  photoFilename,
} = {}) {
  if (!company || !locationKey || !photoFilename) return null;
  const params = new URLSearchParams();
  if (environment) params.set("environment", environment);
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  params.set("photo_filename", photoFilename);
  const encodedLocation = encodeURIComponent(locationKey);
  return apiRequest(`/api/assets/mockup-frames/${company}/${encodedLocation}?${params.toString()}`, {
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

export function getTemplatePhotoUrl(location, photo, { company, venueType } = {}) {
  if (!location || !photo) return "";
  // location is path param (supports slashes like "network/type/asset"), photo is query param
  // company is optional hint for O(1) lookup (avoids searching all companies)
  const params = new URLSearchParams();
  params.set("photo_filename", photo);
  if (company) params.set("company", company);
  if (venueType) params.set("venue_type", venueType);
  return `${runtimeConfig.API_BASE_URL}/api/sales/mockup/photo/${location}?${params.toString()}`;
}

// TODO : This endpoint does not exist in backend now.
export async function getHistory() {
  return apiRequest("/api/sales/mockup/history");
}

export async function getTemplatePhotoBlob(location, photo, { timeOfDay, side, company, venueType } = {}) {
  if (!location || !photo) return null;
  const params = new URLSearchParams();
  params.set("photo_filename", photo);  // Required query param
  if (timeOfDay) params.set("time_of_day", timeOfDay);
  if (side) params.set("side", side);
  if (company) params.set("company", company);  // O(1) lookup hint
  if (venueType) params.set("venue_type", venueType);
  // location is path param (supports slashes like "network/type/asset"), photo is query param
  const path = `/api/sales/mockup/photo/${location}?${params.toString()}`;
  return apiBlob(path);
}

export async function getTemplatePhotoBlobUrl(location, photo, { timeOfDay, side, company, venueType } = {}) {
  const blob = await getTemplatePhotoBlob(location, photo, { timeOfDay, side, company, venueType });
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
