import { apiRequest } from "./http";

export async function getDashboard() {
  return apiRequest("/api/admin/dashboard");
}

export async function getUsers({ limit = 100, offset = 0 } = {}) {
  return apiRequest(`/api/rbac/users`); //?limit=${limit}&offset=${offset}`);
}

export async function getUser(userId) {
  return apiRequest(`/api/rbac/user/${userId}`);
}

export async function getrbacUser(userId) {
  return apiRequest(`/api/rbac/user/${userId}`);
}

export async function getUserPermissions(userId) {
  return apiRequest(`/api/rbac/users/${userId}/permissions`);
}

export async function createUser(userData) {
  return apiRequest("/api/rbac/users", { method: "POST", body: JSON.stringify(userData) });
}

export async function updateUser(userId, userData) {
  return apiRequest(`/api/rbac/users/${userId}`, { method: "PUT", body: JSON.stringify(userData) });
}

export async function deleteUser(userId) {
  return apiRequest(`/api/rbac/users/${userId}`, { method: "DELETE" });
}

export async function deactivateUser(userId) {
  return apiRequest(`/api/rbac/users/${encodeURIComponent(userId)}/deactivate`, { method: "POST" });
}

export async function reactivateUser(userId) {
  return apiRequest(`/api/rbac/users/${encodeURIComponent(userId)}/reactivate`, { method: "POST" });
}

export async function getProfiles() {
  return apiRequest("/api/rbac/profiles");
}

export async function createProfile(profileData) {
  return apiRequest("/api/rbac/profiles", { method: "POST", body: JSON.stringify(profileData) });
}

export async function updateProfile(profileId, profileData) {
  return apiRequest(`/api/rbac/profiles/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    body: JSON.stringify(profileData),
  });
}

export async function deleteProfile(profileId) {
  return apiRequest(`/api/rbac/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
}

export async function getTeams() {
  return apiRequest("/api/rbac/teams");
}

export async function setUserPermissions(userId, permissions) {
  return apiRequest(`/api/rbac/users/${userId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permissions }),
  });
}

export async function getPermissions() {
  const data = await apiRequest("/api/rbac/permissions");
  return data;
}

export async function addPermission(value, description) {
  return apiRequest("/api/rbac/permissions", {
    method: "POST",
    body: JSON.stringify({ name: value, description }),
  });
}

export async function deletePermission(value) {
  return apiRequest(`/api/rbac/permissions/${encodeURIComponent(value)}`, {
    method: "DELETE",
  });
}

export async function getUserPermissionSets(userId) {
  if (!userId) return [];
  return apiRequest(`/api/rbac/users/${encodeURIComponent(userId)}/permission-sets`);
}

export async function assignUserPermissionSet(userId, payload) {
  if (!userId) return null;
  return apiRequest(`/api/rbac/users/${encodeURIComponent(userId)}/permission-sets`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeUserPermissionSet(userId, setId) {
  if (!userId || !setId) return null;
  return apiRequest(`/api/rbac/users/${encodeURIComponent(userId)}/permission-sets/${encodeURIComponent(setId)}`, {
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
  const data = await apiRequest("/api/rbac/companies");
  return data.companies || data;
}

export async function getCompanyHierarchy() {
  return apiRequest("/api/rbac/companies/hierarchy");
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
