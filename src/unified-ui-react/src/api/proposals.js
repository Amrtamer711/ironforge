import { apiRequest } from "./http";

export async function generate(data) {
  return apiRequest("/api/sales/proposals", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getLocations({ service, displayType } = {}) {
  const params = new URLSearchParams();
  if (service) params.set("service", service);
  if (displayType) params.set("display_type", displayType);
  const query = params.toString();
  return apiRequest(`/api/sales/locations${query ? `?${query}` : ""}`);
}

export async function getLocationByKey(locationKey) {
  if (!locationKey) return null;
  return apiRequest(`/api/sales/locations/${encodeURIComponent(locationKey)}`);
}

export async function getHistory() {
  return apiRequest("/api/sales/proposals/history");
}
