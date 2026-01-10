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

/**
 * Fetch chat history with optional pagination.
 * @param {Object} options - Pagination options
 * @param {number} [options.limit] - Max messages to return
 * @param {number} [options.offset=0] - Messages to skip
 * @param {boolean} [options.newestFirst=false] - If true, offset counts from end (for infinite scroll)
 * @param {AbortSignal} [options.signal] - Optional abort signal to cancel the request
 * @returns {Promise<{messages: Array, session_id: string, message_count: number, has_more: boolean, attachment_file_ids: string[]}>}
 */
export async function getHistory({ limit, offset = 0, newestFirst = false, signal } = {}) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", limit);
  if (offset > 0) params.set("offset", offset);
  if (newestFirst) params.set("newest_first", "true");

  const query = params.toString();
  return apiRequest(`/api/sales/chat/history${query ? `?${query}` : ""}`, { signal });
}

/**
 * Batch refresh signed URLs for chat attachments.
 * Supports pre-fetching: pass prefetchIds for next batch to load ahead.
 * @param {string[]} fileIds - Currently visible attachment file_ids
 * @param {string[]} prefetchIds - Next batch to pre-fetch (optional)
 * @returns {Promise<{urls: Record<string, string>}>}
 */
export async function refreshAttachmentUrls(fileIds, prefetchIds = []) {
  return apiRequest("/api/sales/chat/attachments/refresh", {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds, prefetch_ids: prefetchIds }),
  });
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
