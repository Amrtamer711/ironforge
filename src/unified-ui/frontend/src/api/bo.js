import { apiRequest } from "./http";

export async function getPending() {
  return apiRequest("/api/sales/bo/pending");
}

export async function approve(id) {
  return apiRequest(`/api/sales/bo/${id}/approve`, { method: "POST" });
}

export async function reject(id, reason) {
  return apiRequest(`/api/sales/bo/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
