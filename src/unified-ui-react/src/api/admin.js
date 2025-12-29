import { apiRequest } from "./http";

export async function getDashboard() {
  return apiRequest("/api/admin/dashboard");
}

export async function getUsers({ limit = 100, offset = 0 } = {}) {
  return apiRequest(`/api/admin/users`); //?limit=${limit}&offset=${offset}`);
}

export async function getUser(userId) {
  return apiRequest(`/api/admin/users/${userId}`);
}

export async function getrbacUser(userId) {
  return apiRequest(`/api/rbac/user/${userId}`);
}

export async function getUserPermissions(userId) {
  return apiRequest(`/api/admin/users/${userId}/permissions`);
}

export async function createUser(userData) {
  return apiRequest("/api/admin/users", { method: "POST", body: JSON.stringify(userData) });
}

export async function updateUser(userId, userData) {
  return apiRequest(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(userData) });
}

export async function deleteUser(userId) {
  return apiRequest(`/api/admin/users/${userId}`, { method: "DELETE" });
}

export async function getProfiles() {
  return apiRequest("/api/admin/profiles");
}

export async function createProfile(profileData) {
  return apiRequest("/api/admin/profiles", { method: "POST", body: JSON.stringify(profileData) });
}

export async function updateProfile(profileName, profileData) {
  return apiRequest(`/api/admin/profiles/${profileName}`, { method: "PUT", body: JSON.stringify(profileData) });
}

export async function deleteProfile(profileName) {
  return apiRequest(`/api/admin/profiles/${profileName}`, { method: "DELETE" });
}

export async function getTeams() {
  return apiRequest("/api/admin/teams");
}

export async function setUserPermissions(userId, permissions) {
  return apiRequest(`/api/admin/users/${userId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permissions }),
  });
}

export async function getPermissions() {
  const data = await apiRequest("/api/dev/permissions");
  return data;
}

export async function addPermission(value, description) {
  return apiRequest("/api/dev/permissions/add", {
    method: "POST",
    body: JSON.stringify({ name: value, description }),
  });
}

export async function deletePermission(value) {
  return apiRequest(`/api/dev/permissions/${encodeURIComponent(value)}`, {
    method: "DELETE",
  });
}

// Invites (old admin.js used /api/base/auth/invites)
export async function getInvites({ includeUsed = false } = {}) {
  return apiRequest(`/api/base/auth/invites?include_used=${includeUsed}`);
}

export async function createInvite(payload) {
  return apiRequest("/api/base/auth/invites", { method: "POST", body: JSON.stringify(payload) });
}

export async function getApiKeys({ includeInactive = false } = {}) {
  return apiRequest(`/api/admin/api-keys?include_inactive=${includeInactive}`);
}

export async function createApiKey(payload) {
  return apiRequest("/api/admin/api-keys", { method: "POST", body: JSON.stringify(payload) });
}

export async function getCompanies() {
  return apiRequest("/api/dev/companies");
}

export async function createCompany(payload) {
  return apiRequest("/api/dev/companies/add", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateCompany(code, payload) {
  return apiRequest(`/api/admin/company/${encodeURIComponent(code)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteCompany(code) {
  return apiRequest(`/api/dev/companies/${encodeURIComponent(code)}`, { method: "DELETE" });
}

export async function getPermissionSets() {
  return apiRequest("/api/rbac/permission-sets");
}

export async function createPermissionSet(payload) {
  return apiRequest("/api/rbac/permission-sets", { method: "POST", body: JSON.stringify(payload) });
}

export async function updatePermissionSet(name, payload) {
  return apiRequest(`/api/rbac/permission-sets/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deletePermissionSet(name) {
  return apiRequest(`/api/rbac/permission-sets/${encodeURIComponent(name)}`, { method: "DELETE" });
}
