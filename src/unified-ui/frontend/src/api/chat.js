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

/**
 * Resume streaming from a previous request after page refresh.
 *
 * This function attempts to reconnect to an in-progress or recently completed
 * request and retrieve any events that occurred since the last seen event.
 *
 * @param {Object} options - Resume options
 * @param {string} options.requestId - The unique request ID from the original stream
 * @param {number} [options.eventIndex=0] - Index of the last processed event
 * @param {function} options.onEvent - Callback for each event
 * @param {function} options.onDone - Callback when stream completes
 * @param {function} options.onError - Callback for errors
 * @param {function} options.onNotFound - Callback when request not found/expired
 * @param {AbortSignal} [options.signal] - Optional abort signal
 * @returns {Promise<{status: string, events?: Array}>}
 */
export async function resumeStream({
  requestId,
  eventIndex = 0,
  onEvent,
  onDone,
  onError,
  onNotFound,
  signal,
}) {
  try {
    const token = getAuthToken();
    const base = runtimeConfig.API_BASE_URL || "";
    const url = `${base}/api/sales/chat/resume/${requestId}?event_index=${eventIndex}`;

    const res = await fetch(url, {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal,
    });

    if (res.status === 401) {
      clearAuthToken();
      window.dispatchEvent(new CustomEvent("auth:logout"));
      onError?.(new Error("Unauthorized"));
      return { status: "error" };
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `API error: ${res.status}`);
    }

    // Check content type to determine if this is JSON or SSE
    const contentType = res.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      // Completed request - JSON response with buffered events
      const data = await res.json();

      if (data.status === "not_found") {
        onNotFound?.();
        return { status: "not_found" };
      }

      if (data.status === "completed") {
        // Process buffered events
        for (const evt of data.events || []) {
          onEvent?.(evt);
        }
        onDone?.();
        return { status: "completed", events: data.events };
      }

      return data;
    } else if (contentType.includes("text/event-stream")) {
      // Still running - SSE stream
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
          } catch {
            // Ignore parse errors
          }
        }
      }

      if (!ended) onDone?.();
      return { status: "streaming_completed" };
    }

    // Unknown response type
    return { status: "unknown" };
  } catch (e) {
    if (e.name === "AbortError") {
      return { status: "aborted" };
    }
    onError?.(e);
    return { status: "error", error: e.message };
  }
}
