import { apiRequest } from "./http";

export async function checkSession() {
  return apiRequest("/api/base/auth/session");
}

export async function me() {
  return apiRequest("/api/base/auth/me");
}
