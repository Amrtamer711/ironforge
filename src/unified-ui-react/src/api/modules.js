import { apiRequest } from "./http";

export async function getAccessibleModules() {
  return apiRequest("/api/modules/accessible", { method: "GET" });
}
