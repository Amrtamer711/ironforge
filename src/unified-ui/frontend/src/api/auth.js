import { apiRequest } from "./http";

export async function login(email, password) {
  return apiRequest("/api/sales/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout() {
  return apiRequest("/api/sales/auth/logout", { method: "POST" });
}

export async function me() {
  return apiRequest("/api/sales/auth/me");
}
