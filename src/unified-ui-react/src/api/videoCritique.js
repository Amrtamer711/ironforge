import { apiRequest } from "./http";
import { clearAuthToken, getAuthToken } from "../lib/token";
import { runtimeConfig } from "../lib/runtimeConfig";
import * as mockApi from "./videoCritiqueMock";

const USE_MOCK = true;

function unescapePythonString(value) {
  if (!value) return "";
  return value
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, "\\");
}

function parseSsePayload(payload) {
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    const typeMatch = payload.match(/"type"\s*:\s*"([^"]+)"/);
    const contentMatch = payload.match(/"content"\s*:\s*'([\s\S]*?)'/);
    const messageMatch = payload.match(/"message"\s*:\s*'([\s\S]*?)'/);
    const nameMatch = payload.match(/"name"\s*:\s*"([^"]+)"/);
    const sessionMatch = payload.match(/"session_id"\s*:\s*"([^"]+)"/);

    if (!typeMatch && !contentMatch && !messageMatch) {
      return { content: payload };
    }

    return {
      type: typeMatch ? typeMatch[1] : undefined,
      content: contentMatch ? unescapePythonString(contentMatch[1]) : undefined,
      message: messageMatch ? unescapePythonString(messageMatch[1]) : undefined,
      name: nameMatch ? nameMatch[1] : undefined,
      session_id: sessionMatch ? sessionMatch[1] : undefined,
    };
  }
}

export async function getDashboardOverview() {
  if (USE_MOCK) return mockApi.getDashboardOverview();

  const [stats, workload, upcoming, byStatus, byLocation, byVideographer] = await Promise.all([
    // TODO: expecting GET /api/dashboard/stats -> { ... }
    apiRequest("/api/dashboard/stats"),
    // TODO: expecting GET /api/dashboard/workload -> { ... }
    apiRequest("/api/dashboard/workload"),
    // TODO: expecting GET /api/dashboard/upcoming-shoots -> { ... }
    apiRequest("/api/dashboard/upcoming-shoots"),
    // TODO: expecting GET /api/dashboard/by-status -> { ... }
    apiRequest("/api/dashboard/by-status"),
    // TODO: expecting GET /api/dashboard/by-location -> { ... }
    apiRequest("/api/dashboard/by-location"),
    // TODO: expecting GET /api/dashboard/by-videographer -> { ... }
    apiRequest("/api/dashboard/by-videographer"),
  ]);

  return { stats, workload, upcoming, byStatus, byLocation, byVideographer };
}

export async function getDashboardFull(params) {
  if (USE_MOCK) return mockApi.getDashboardFull(params);
  const search = new URLSearchParams();
  if (params?.mode) search.set("mode", params.mode);
  if (params?.period) search.set("period", params.period);
  const query = search.toString();
  // TODO: expecting GET /api/dashboard?mode=...&period=... -> { summary, tasks, reviewer, pie, ... }
  return apiRequest(`/api/dashboard${query ? `?${query}` : ""}`);
}

export async function getDashboardStats() {
  if (USE_MOCK) return mockApi.getDashboardStats();
  // TODO: expecting GET /api/dashboard/stats -> { ... }
  return apiRequest("/api/dashboard/stats");
}

export async function getDashboardWorkload() {
  if (USE_MOCK) return mockApi.getDashboardWorkload();
  // TODO: expecting GET /api/dashboard/workload -> { ... }
  return apiRequest("/api/dashboard/workload");
}

export async function getDashboardUpcomingShoots() {
  if (USE_MOCK) return mockApi.getDashboardUpcomingShoots();
  // TODO: expecting GET /api/dashboard/upcoming-shoots -> { ... }
  return apiRequest("/api/dashboard/upcoming-shoots");
}

export async function getDashboardByStatus() {
  if (USE_MOCK) return mockApi.getDashboardByStatus();
  // TODO: expecting GET /api/dashboard/by-status -> { ... }
  return apiRequest("/api/dashboard/by-status");
}

export async function getDashboardByLocation() {
  if (USE_MOCK) return mockApi.getDashboardByLocation();
  // TODO: expecting GET /api/dashboard/by-location -> { ... }
  return apiRequest("/api/dashboard/by-location");
}

export async function getDashboardByVideographer() {
  if (USE_MOCK) return mockApi.getDashboardByVideographer();
  // TODO: expecting GET /api/dashboard/by-videographer -> { ... }
  return apiRequest("/api/dashboard/by-videographer");
}

export async function getHistory() {
  if (USE_MOCK) return mockApi.getHistory();
  // TODO: expecting GET /api/chat/history -> { messages, session_id, message_count, last_updated }
  return apiRequest("/api/chat/history");
}

export async function uploadFile({ file, message, sessionId }) {
  if (USE_MOCK) return mockApi.uploadFile({ file, message, sessionId });

  const formData = new FormData();
  formData.append("file", file);
  if (message) formData.append("message", message);
  if (sessionId) formData.append("session_id", sessionId);

  // TODO: expecting POST /api/chat/upload (multipart) -> { success, file_id, file_url?, type, response?, message?, session_id }
  return apiRequest("/api/chat/upload", { method: "POST", body: formData });
}

export async function uploadAttachment({ file }) {
  if (USE_MOCK) return mockApi.uploadAttachment({ file });

  const formData = new FormData();
  formData.append("file", file);

  // TODO: expecting POST /api/chat/files/upload (multipart) -> { file_id, filename, file_url }
  return apiRequest("/api/chat/files/upload", { method: "POST", body: formData });
}

export async function uploadVideo({ file, taskNumber }) {
  if (USE_MOCK) return mockApi.uploadVideo({ file, taskNumber });

  const formData = new FormData();
  formData.append("file", file);
  formData.append("task_number", String(taskNumber));

  // TODO: expecting POST /api/videos/upload (multipart) -> { success, file_id, workflow_id, version, message }
  return apiRequest("/api/videos/upload", { method: "POST", body: formData });
}

export async function sendCommand({ command, args, sessionId }) {
  if (USE_MOCK) return mockApi.sendCommand({ command, args, sessionId });

  // TODO: expecting POST /api/chat/command -> { success, command, response?, error?, session_id }
  return apiRequest("/api/chat/command", {
    method: "POST",
    body: JSON.stringify({
      command,
      args,
      session_id: sessionId,
    }),
  });
}

export async function sendAction({ actionId, workflowId }) {
  if (USE_MOCK) return mockApi.sendAction({ actionId, workflowId });

  // TODO: expecting POST /api/chat/action -> { success, message, requires_form, form_type, workflow_id }
  return apiRequest("/api/chat/action", {
    method: "POST",
    body: JSON.stringify({
      action_id: actionId,
      workflow_id: workflowId,
    }),
  });
}

export async function submitForm({ formType, workflowId, category, reason }) {
  if (USE_MOCK) return mockApi.submitForm({ formType, workflowId, category, reason });

  // TODO: expecting POST /api/chat/form -> { success, message }
  return apiRequest("/api/chat/form", {
    method: "POST",
    body: JSON.stringify({
      form_type: formType,
      workflow_id: workflowId,
      category,
      reason,
    }),
  });
}

export async function getFormConfig(formType) {
  if (USE_MOCK) return mockApi.getFormConfig(formType);

  // TODO: expecting GET /api/chat/forms/{formType} -> { title, submit_text, fields[] }
  return apiRequest(`/api/chat/forms/${encodeURIComponent(formType)}`);
}

export async function getPendingWorkflows() {
  if (USE_MOCK) return mockApi.getPendingWorkflows();

  // TODO: expecting GET /api/chat/workflows/pending -> { count, workflows[] }
  return apiRequest("/api/chat/workflows/pending");
}

export async function getWorkflowStatus(workflowId) {
  if (USE_MOCK) return mockApi.getWorkflowStatus(workflowId);

  // TODO: expecting GET /api/chat/workflows/{workflowId} -> { workflow_id, task_number, status, reviewer_approved, hos_approved }
  return apiRequest(`/api/chat/workflows/${workflowId}`);
}

export function resolveFileUrl(file) {
  if (USE_MOCK) return mockApi.resolveFileUrl(file);

  const base = runtimeConfig.API_BASE_URL || "";
  if (file?.preview_url) return file.preview_url;
  if (file?.file_url) {
    if (file.file_url.startsWith("http")) return file.file_url;
    return `${base}${file.file_url}`;
  }
  if (file?.url) {
    if (file.url.startsWith("http")) return file.url;
    return `${base}${file.url}`;
  }
  if (file?.file_id) {
    // TODO: expecting GET /api/chat/files/{file_id}/{filename}
    return `${base}/api/chat/files/${file.file_id}/${encodeURIComponent(file.filename || "file")}`;
  }
  return null;
}

export async function streamMessage({ sessionId, message, fileIds, onEvent, onDone, onError, signal }) {
  if (USE_MOCK) {
    return mockApi.streamMessage({ sessionId, message, fileIds, onEvent, onDone, onError, signal });
  }

  try {
    const token = getAuthToken();
    const base = runtimeConfig.API_BASE_URL || "";
    // TODO: expecting POST /api/chat/message/stream (SSE) -> data: { type, content, files?, actions?, session_id }
    const res = await fetch(`${base}/api/chat/message/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        ...(fileIds?.length ? { file_ids: fileIds } : {}),
      }),
      signal,
    });

    if (res.status === 401) {
      clearAuthToken();
      window.dispatchEvent(new CustomEvent("auth:logout"));
      onError?.(new Error("Unauthorized"));
      return;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `API error: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let ended = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const raw of lines) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        const payload = line.replace(/^data:\s?/, "");
        if (!payload) continue;

        const evt = parseSsePayload(payload);
        if (!evt) continue;
        onEvent?.(evt);

        if (evt.type === "done") {
          ended = true;
          onDone?.();
        }

        if (evt.type === "error") {
          onError?.(new Error(evt.message || "Stream error"));
        }
      }
    }

    if (!ended) onDone?.();
  } catch (e) {
    onError?.(e);
    throw e;
  }
}
