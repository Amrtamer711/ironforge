import { apiRequest } from "./http";
import { clearAuthToken, getAuthToken } from "../lib/token";
import { runtimeConfig } from "../lib/runtimeConfig";

// Legacy-compatible endpoints
export async function sendMessage(conversationId, message) {
  return apiRequest("/api/sales/chat/message", {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}

export async function getConversations() {
  return apiRequest("/api/sales/chat/conversations");
}

export async function getConversation(id) {
  return apiRequest(`/api/sales/chat/conversation/${id}`);
}

export async function createConversation() {
  return apiRequest("/api/sales/chat/conversation", { method: "POST" });
}

export async function deleteConversation(id) {
  return apiRequest(`/api/sales/chat/conversation/${id}`, { method: "DELETE" });
}

export async function getHistory() {
  return apiRequest("/api/sales/chat/history");
}

// SSE stream (legacy-compatible)
export async function streamMessage({ conversationId, message, fileIds, onEvent, onChunk, onDone, onError, signal }) {
  try {
    const token = getAuthToken();
    const base = runtimeConfig.API_BASE_URL || "";
    const res = await fetch(`${base}/api/sales/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
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
        if (!payload || payload === "[DONE]") {
          ended = true;
          onDone?.();
          continue;
        }

        try {
          const evt = JSON.parse(payload);
          onEvent?.(evt);
          if (!onEvent && onChunk) {
            if (evt.type === "chunk" || evt.type === "content") {
              onChunk(evt);
            }
          }
        } catch {
          const fallback = { content: payload };
          onEvent?.(fallback);
          if (!onEvent) onChunk?.(fallback);
        }
      }
    }

    if (!ended) onDone?.();
  } catch (e) {
    onError?.(e);
    throw e;
  }
}
