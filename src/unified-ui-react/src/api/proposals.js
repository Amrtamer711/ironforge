import { apiRequest } from "./http";

export async function generate(data) {
  return apiRequest("/api/sales/proposals/generate", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getHistory() {
  return apiRequest("/api/sales/proposals/history");
}
