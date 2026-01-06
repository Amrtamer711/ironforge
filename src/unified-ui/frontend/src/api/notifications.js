import { apiRequest } from "./http";

// Backend endpoints expected:
// GET    /api/notifications
// POST   /api/notifications
// DELETE /api/notifications
// DELETE /api/notifications/:id
// PATCH  /api/notifications/:id  { read: true }

const STORAGE_KEY = "mmg-notifications";
const BASE_PATH = "/api/notifications";

function safeParse(value, fallback) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function loadNotifications() {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(STORAGE_KEY);
  const list = safeParse(raw, []);
  return Array.isArray(list) ? list : [];
}

function saveNotifications(list) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

function buildNotification(input) {
  const now = new Date().toISOString();
  const id =
    input?.id ||
    (typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `ntf_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`);
  return {
    id,
    title: input?.title || "Notification",
    message: input?.message || "",
    created_at: input?.created_at || now,
    read: Boolean(input?.read),
    level: input?.level || "info",
    meta: input?.meta || {},
  };
}

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.notifications)) return data.notifications;
  if (Array.isArray(data?.data)) return data.data;
  return [];
}

export function getNotifications() {
  return apiRequest(BASE_PATH)
    .then((data) => normalizeList(data))
    .catch(() => loadNotifications());
}

export function addNotification(input) {
  return apiRequest(BASE_PATH, { method: "POST", body: JSON.stringify(input || {}) })
    .then((data) => data?.notification || data?.data || data || buildNotification(input))
    .catch(() => {
      const list = loadNotifications();
      const notification = buildNotification(input);
      const next = [notification, ...list];
      saveNotifications(next);
      return notification;
    });
}

export function clearNotifications() {
  return apiRequest(BASE_PATH, { method: "DELETE" })
    .then(() => [])
    .catch(() => {
      saveNotifications([]);
      return [];
    });
}

export function dismissNotification(id) {
  if (!id) return Promise.resolve(loadNotifications());
  return apiRequest(`${BASE_PATH}/${encodeURIComponent(id)}`, { method: "DELETE" })
    .then(() => loadNotifications())
    .catch(() => {
      const next = loadNotifications().filter((item) => item.id !== id);
      saveNotifications(next);
      return next;
    });
}

export function markNotificationRead(id) {
  if (!id) return Promise.resolve(loadNotifications());
  return apiRequest(`${BASE_PATH}/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ read: true }),
  })
    .then(() => loadNotifications())
    .catch(() => {
      const next = loadNotifications().map((item) => (item.id === id ? { ...item, read: true } : item));
      saveNotifications(next);
      return next;
    });
}

export const NOTIFICATIONS_STORAGE_KEY = STORAGE_KEY;
