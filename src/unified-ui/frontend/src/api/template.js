import { apiRequest } from "./http";

export async function getAll() {
  return apiRequest("/api/sales/templates");
}

export async function get(locationKey) {
  return apiRequest(`/api/sales/templates/${locationKey}`);
}

export async function save(data) {
  return apiRequest("/api/sales/templates", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function remove(id) {
  return apiRequest(`/api/sales/templates/${id}`, { method: "DELETE" });
}

export async function uploadImage(formData) {
  // legacy uses multipart; apiRequest supports FormData
  return apiRequest("/api/sales/templates/upload", {
    method: "POST",
    body: formData,
  });
}

// Legacy naming compatibility
export async function del(id) {
  return remove(id);
}
