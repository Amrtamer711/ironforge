import { apiRequest } from "./http";

function appendArray(params, key, values) {
  if (!Array.isArray(values)) return;
  values.filter(Boolean).forEach((value) => params.append(key, value));
}

export async function getNetworks({ companies, activeOnly = true } = {}) {
  const params = new URLSearchParams();
  appendArray(params, "companies", companies);
  if (activeOnly !== undefined) params.set("active_only", String(activeOnly));
  const query = params.toString();
  return apiRequest(`/api/assets/networks${query ? `?${query}` : ""}`);
}

export async function getAssetTypes({ companies, networkId, activeOnly = true } = {}) {
  const params = new URLSearchParams();
  appendArray(params, "companies", companies);
  if (networkId !== undefined && networkId !== null) params.set("network_id", String(networkId));
  if (activeOnly !== undefined) params.set("active_only", String(activeOnly));
  const query = params.toString();
  return apiRequest(`/api/assets/asset-types${query ? `?${query}` : ""}`);
}

export async function getNetworkAssets({ companies, networkId, typeId, activeOnly = true } = {}) {
  const params = new URLSearchParams();
  appendArray(params, "companies", companies);
  if (networkId !== undefined && networkId !== null) params.set("network_id", String(networkId));
  if (typeId !== undefined && typeId !== null) params.set("type_id", String(typeId));
  if (activeOnly !== undefined) params.set("active_only", String(activeOnly));
  const query = params.toString();
  return apiRequest(`/api/assets/network-assets${query ? `?${query}` : ""}`);
}

export async function getLocations({ companies, networkId, typeId, activeOnly = true, includeEligibility = false } = {}) {
  const params = new URLSearchParams();
  appendArray(params, "companies", companies);
  if (networkId !== undefined && networkId !== null) params.set("network_id", String(networkId));
  if (typeId !== undefined && typeId !== null) params.set("type_id", String(typeId));
  if (activeOnly !== undefined) params.set("active_only", String(activeOnly));
  if (includeEligibility !== undefined) params.set("include_eligibility", String(includeEligibility));
  const query = params.toString();
  return apiRequest(`/api/assets/locations${query ? `?${query}` : ""}`);
}

export async function getPackages({ companies, activeOnly = true } = {}) {
  const params = new URLSearchParams();
  appendArray(params, "companies", companies);
  if (activeOnly !== undefined) params.set("active_only", String(activeOnly));
  const query = params.toString();
  return apiRequest(`/api/assets/packages${query ? `?${query}` : ""}`);
}
