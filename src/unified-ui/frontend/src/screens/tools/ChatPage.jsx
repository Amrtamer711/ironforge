import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Virtuoso } from "react-virtuoso";
import { ExternalLink, Download, FileText, ImageIcon, Loader2, Paperclip, Send } from "lucide-react";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import * as chatApi from "../../api/chat";
import * as filesApi from "../../api/files";
import { getAuthToken } from "../../lib/token";

// =============================================================================
// Global Image Cache - Tracks loaded images to prevent flash on remount
// =============================================================================
// This Set lives OUTSIDE React components. When Virtuoso unmounts items during
// scroll, then remounts them, the component checks this cache first. If the
// image URL is already cached, we skip the placeholder entirely - no flash.
const loadedImagesCache = new Set();

export function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [value, setValue] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState(null);

  const fileRef = useRef(null);
  const abortRef = useRef(null);
  const virtuosoRef = useRef(null);

  // Load history on mount
  useEffect(() => {
    async function loadHistory() {
      try {
        const history = await chatApi.getHistory({ limit: 500 });
        if (history?.messages?.length) {
          setMessages(history.messages.map(normalizeMessage));
          setConversationId(history.session_id || null);
        } else {
          setMessages([createGreeting()]);
        }
      } catch (err) {
        console.error("[ChatPage] Failed to load history:", err);
        setMessages([createGreeting()]);
      } finally {
        setLoading(false);
        // Ensure scroll to bottom after render
        requestAnimationFrame(() => {
          virtuosoRef.current?.scrollToIndex({ index: "LAST", behavior: "auto" });
        });
      }
    }
    loadHistory();
  }, []);

  const canSend = useMemo(
    () => (value.trim().length > 0 || Boolean(pendingFile)) && !streaming,
    [value, pendingFile, streaming]
  );

  const scrollToBottom = useCallback((immediate = false) => {
    if (immediate) {
      virtuosoRef.current?.scrollToIndex({ index: "LAST", behavior: "auto" });
    } else {
      virtuosoRef.current?.scrollToIndex({ index: "LAST", behavior: "smooth", align: "end" });
    }
  }, []);

  // Stable render function for Virtuoso - prevents re-creation on every render
  // contain: 'layout' isolates layout calculations to prevent reflow propagation
  const renderMessage = useCallback((_, msg) => (
    <div className="px-2 py-1.5" style={{ contain: 'layout' }}>
      <Message msg={msg} />
    </div>
  ), []);

  async function send() {
    if (!canSend) return;

    const userText = value.trim();
    const outgoingMessage = userText || (pendingFile ? `Please process this file: ${pendingFile.name}` : "");

    const userMsgId = crypto.randomUUID();
    const userMsg = {
      id: userMsgId,
      role: "user",
      content: userText,
      files: pendingFile ? [{
        filename: pendingFile.name,
        preview_url: URL.createObjectURL(pendingFile),
      }] : [],
      status: null,
    };

    const assistantMsgId = crypto.randomUUID();
    const assistantMsg = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      files: [],
      status: "Thinking",
    };

    setMessages(m => [...m, userMsg, assistantMsg]);
    setValue("");
    const fileToUpload = pendingFile;
    setPendingFile(null);
    // Immediate scroll to show user message, then smooth follow during streaming
    requestAnimationFrame(() => scrollToBottom(true));

    try {
      setStreaming(true);
      abortRef.current?.abort?.();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      let fileIds = [];
      let fullContent = "";

      // Upload file if present
      if (fileToUpload) {
        const uploaded = await filesApi.uploadFile(fileToUpload);
        if (!uploaded?.file_id) throw new Error("Upload failed");
        fileIds = [uploaded.file_id];

        // Update user message with uploaded file info
        setMessages(prev => prev.map(m =>
          m.id === userMsgId ? {
            ...m,
            files: [{
              file_id: uploaded.file_id,
              filename: fileToUpload.name,
              url: uploaded.url,
              width: uploaded.image_width,
              height: uploaded.image_height,
              preview_url: m.files?.[0]?.preview_url,
            }]
          } : m
        ));
      }

      // Stream response
      await chatApi.streamMessage({
        conversationId,
        message: outgoingMessage,
        fileIds,
        signal: ctrl.signal,
        onEvent: (evt) => {
          if (ctrl.signal.aborted) return;

          if (evt?.conversation_id) {
            setConversationId(prev => prev || evt.conversation_id);
          }

          if (evt?.error) {
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: null, content: `Error: ${evt.error}` } : m
            ));
            return;
          }

          if (evt?.type === "status") {
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: evt.content || "Processing" } : m
            ));
            return;
          }

          if (evt?.type === "delete") {
            fullContent = "";
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: "Thinking", content: "" } : m
            ));
            return;
          }

          if (evt?.type === "tool_call") {
            const toolName = evt.tool?.name || "processing";
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: `Processing ${toolName}` } : m
            ));
            return;
          }

          if ((evt?.type === "chunk" || evt?.type === "content") && evt.content) {
            fullContent = evt.type === "content" ? evt.content : fullContent + evt.content;
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: null, content: fullContent } : m
            ));
            return;
          }

          if (evt?.content && !evt.type) {
            fullContent += evt.content;
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, status: null, content: fullContent } : m
            ));
            return;
          }

          if ((evt?.type === "files" || evt?.type === "file") && (evt.files || evt.file)) {
            const newFiles = evt.files || [evt.file || evt];
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId ? { ...m, files: [...(m.files || []), ...newFiles] } : m
            ));
            return;
          }
        },
        onDone: () => {
          if (!fullContent) {
            setMessages(prev => prev.map(m =>
              m.id === assistantMsgId && !m.content && !m.files?.length
                ? { ...m, status: null, content: "I'm ready to help. What would you like to do?" }
                : m.id === assistantMsgId ? { ...m, status: null } : m
            ));
          }
        },
      });
    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === assistantMsgId ? { ...m, status: null, content: e?.message || "Failed to get response" } : m
      ));
    } finally {
      setStreaming(false);
    }
  }

  if (loading) {
    return (
      <div className="h-full flex flex-col gap-4 min-h-0">
        <Card className="p-4 overflow-hidden flex-1 min-h-0 flex items-center justify-center">
          <div className="text-center">
            <Loader2 className="animate-spin mx-auto mb-2" size={32} />
            <p className="text-sm text-black/50 dark:text-white/50">Loading conversation...</p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-4 min-h-0">
      <Card className="p-4 overflow-hidden flex-1 min-h-0">
        <Virtuoso
          ref={virtuosoRef}
          className="h-full scrollbar-thin"
          data={messages}
          initialTopMostItemIndex={messages.length - 1}
          followOutput="smooth"
          overscan={200}
          increaseViewportBy={{ top: 200, bottom: 200 }}
          computeItemKey={(_, msg) => msg.id}
          itemContent={renderMessage}
          skipAnimationFrameInResizeObserver={true}
        />
      </Card>

      <Card className="p-3">
        {pendingFile && (
          <div className="mb-2 flex items-center justify-between rounded-2xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm">
            <div className="truncate">{pendingFile.name}</div>
            <button className="opacity-70 hover:opacity-100" onClick={() => setPendingFile(null)}>✕</button>
          </div>
        )}

        <div className="flex items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={(e) => setPendingFile(e.target.files?.[0] || null)}
            accept="image/*,.pdf,.xlsx,.xls,.csv,.docx,.doc"
          />

          <Button variant="ghost" size="icon" className="rounded-2xl" title="Attach file" onClick={() => fileRef.current?.click()}>
            <Paperclip size={18} />
          </Button>

          <TextArea value={value} onChange={setValue} placeholder="Type your message..." onEnter={send} />

          <Button size="icon" className="w-12 rounded-2xl" title="Send" disabled={!canSend} onClick={send}>
            <Send size={18} />
          </Button>
        </div>

        <div className="mt-2 text-xs text-black/45 dark:text-white/55">
          AI can make mistakes. Verify important information.
        </div>
      </Card>
    </div>
  );
}

// =============================================================================
// Message Component
// =============================================================================

const Message = React.memo(function Message({ msg }) {
  const isUser = msg.role === "user";
  const formatted = useMemo(() => formatContent(msg.content || ""), [msg.content]);
  const isStatus = Boolean(msg.status);

  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div className={[
        "max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-soft break-words",
        "ring-1 ring-black/5 dark:ring-white/10 backdrop-blur-xs",
        isUser
          ? "bg-black text-white dark:bg-white dark:text-black"
          : "bg-white/70 dark:bg-white/10",
      ].join(" ")}>
        {isStatus ? (
          <StatusLine text={msg.status} />
        ) : (
          <div dangerouslySetInnerHTML={{ __html: formatted }} />
        )}

        {msg.files?.length > 0 && (
          <div className="mt-2 space-y-1">
            {msg.files.map((f, i) => (
              <Attachment key={f.file_id || `file-${i}`} file={f} isUser={isUser} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
});

// =============================================================================
// Attachment Component - Simple image loading with fixed dimensions
// =============================================================================

const Attachment = React.memo(function Attachment({ file, isUser }) {
  const ext = getFileExtension(file.filename || file.url || "");
  const isImage = ["jpg", "jpeg", "png", "gif", "webp", "bmp"].includes(ext);
  const displayName = file.filename || "Attachment";

  // For local files (blob URLs), use preview_url
  // For remote files, use thumbnail_url or url from API
  const imageUrl = file.preview_url || file.thumbnail_url || file.url;
  const fullUrl = file.url || file.preview_url;

  if (isImage && imageUrl) {
    return (
      <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-2">
        <ImageWithPlaceholder
          src={imageUrl}
          fullUrl={fullUrl}
          alt={displayName}
          width={file.width}
          height={file.height}
          isUser={isUser}
        />
        {!isUser && fullUrl && (
          <div className="mt-2 flex items-center gap-2">
            <Button asChild size="sm" variant="ghost" className="rounded-xl">
              <a href={fullUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} className="mr-1" /> Open
              </a>
            </Button>
            <Button size="sm" variant="secondary" className="rounded-xl" onClick={() => downloadFile(fullUrl, displayName)}>
              <Download size={14} className="mr-1" /> Download
            </Button>
          </div>
        )}
      </div>
    );
  }

  // Non-image file
  const isPdf = ext === "pdf";
  return (
    <div className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
            {isPdf ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-0.5">
                <FileText size={12} /> PDF
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-black/5 dark:bg-white/10 px-2 py-0.5">
                {ext ? ext.toUpperCase() : "FILE"}
              </span>
            )}
          </div>
          {!isUser && <div className="mt-1 text-xs font-semibold text-black/80 dark:text-white/85 truncate">{displayName}</div>}
        </div>
        {!isUser && fullUrl && (
          <div className="flex items-center gap-2">
            <Button asChild size="sm" variant="ghost" className="rounded-xl">
              <a href={fullUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} className="mr-1" /> Open
              </a>
            </Button>
            <Button size="sm" variant="secondary" className="rounded-xl" onClick={() => downloadFile(fullUrl, displayName)}>
              <Download size={14} className="mr-1" /> Download
            </Button>
          </div>
        )}
      </div>
    </div>
  );
});

// =============================================================================
// Image with fixed placeholder - dimensions from API prevent layout shift
// Uses global cache to prevent flash when Virtuoso remounts items during scroll
// =============================================================================

const MAX_WIDTH = 400;
const MAX_HEIGHT = 400;
const DEFAULT_WIDTH = 300;
const DEFAULT_HEIGHT = 200;

const ImageWithPlaceholder = React.memo(function ImageWithPlaceholder({ src, fullUrl, alt, width, height, isUser }) {
  // Check global cache FIRST - if image was loaded before, skip placeholder entirely
  // This prevents the flash when Virtuoso remounts items during scrolling
  const alreadyCached = loadedImagesCache.has(src);
  const [loaded, setLoaded] = useState(alreadyCached);
  const [error, setError] = useState(false);

  // Stable callback that adds to global cache when image loads
  const handleLoad = useCallback(() => {
    loadedImagesCache.add(src);
    setLoaded(true);
  }, [src]);

  const handleError = useCallback(() => {
    setError(true);
  }, []);

  // Calculate container size from stored dimensions
  // Using min/max constraints ensures the container never changes size during load
  const containerStyle = useMemo(() => {
    let w, h;
    if (width && height && width > 0 && height > 0) {
      const aspect = width / height;
      if (aspect >= 1) {
        w = Math.min(width, MAX_WIDTH);
        h = Math.round(w / aspect);
      } else {
        h = Math.min(height, MAX_HEIGHT);
        w = Math.round(h * aspect);
      }
    } else {
      w = DEFAULT_WIDTH;
      h = DEFAULT_HEIGHT;
    }
    // Set both width/height AND min/max to lock the container size
    return {
      width: w,
      height: h,
      minWidth: w,
      minHeight: h,
      maxWidth: w,
      maxHeight: h,
    };
  }, [width, height]);

  if (error) {
    return (
      <div className="flex items-center justify-center bg-black/5 dark:bg-white/5 rounded-lg" style={containerStyle}>
        <ImageIcon className="text-red-400" size={24} />
      </div>
    );
  }

  // Use fixed dimensions to prevent layout shift during load
  // contain: 'layout' isolates this element from triggering parent reflows
  const imgElement = (
    <div
      className="overflow-hidden rounded-lg bg-black/5 dark:bg-white/5"
      style={{ ...containerStyle, contain: 'layout' }}
    >
      <img
        src={src}
        alt={alt}
        className={`w-full h-full object-contain transition-opacity duration-150 ${loaded ? 'opacity-100' : 'opacity-0'}`}
        onLoad={handleLoad}
        onError={handleError}
      />
    </div>
  );

  // Wrap in link if not user message and fullUrl available
  if (!isUser && fullUrl) {
    return <a href={fullUrl} target="_blank" rel="noopener noreferrer" className="block">{imgElement}</a>;
  }

  return imgElement;
});

// =============================================================================
// UI Components
// =============================================================================

function TextArea({ value, onChange, placeholder, onEnter }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 132) + "px";
  }, [value]);

  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          onEnter?.();
        }
      }}
      placeholder={placeholder}
      className="w-full resize-none rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 overflow-auto"
      style={{ maxHeight: "132px" }}
    />
  );
}

function StatusLine({ text }) {
  const displayText = (text || "Thinking").replace(/\s*\.{3,}$/, "");
  return (
    <span className="inline-flex items-center gap-2 opacity-80">
      <span>{displayText}</span>
      <span className="mmg-ellipsis" aria-hidden="true">
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "0ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "120ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "240ms" }} />
      </span>
    </span>
  );
}

// =============================================================================
// Utilities
// =============================================================================

function normalizeMessage(msg) {
  return {
    id: msg.id || msg.message_id || crypto.randomUUID(),
    role: msg.role || "assistant",
    content: msg.content || "",
    files: msg.files || msg.attachments || [],
    status: null,
  };
}

function createGreeting() {
  const hour = new Date().getHours();
  const time = hour >= 5 && hour < 12 ? "morning" : hour < 17 ? "afternoon" : hour < 21 ? "evening" : "night";
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: `Good ${time}, how can I help?`,
    files: [],
    status: null,
  };
}

function getFileExtension(value) {
  if (!value) return "";
  const cleaned = String(value).split("?")[0].split("#")[0];
  const parts = cleaned.split(".");
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

async function downloadFile(url, filename) {
  try {
    const token = getAuthToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : undefined });
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  } catch {
    window.open(url, "_blank");
  }
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatContent(content) {
  if (!content) return "";

  // Extract code blocks
  const codeBlocks = [];
  let processed = content.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push({ lang, code: code.trim() });
    return `__CODE_BLOCK_${codeBlocks.length - 1}__`;
  });

  // Extract inline code
  const inlineCodes = [];
  processed = processed.replace(/`([^`]+)`/g, (_, code) => {
    inlineCodes.push(code);
    return `__INLINE_CODE_${inlineCodes.length - 1}__`;
  });

  // Process lines
  const lines = processed.split("\n");
  const result = [];
  let inList = false;
  let listType = null;

  for (const line of lines) {
    // Code block placeholder
    const codeMatch = line.match(/^__CODE_BLOCK_(\d+)__$/);
    if (codeMatch) {
      if (inList) { result.push(listType === "ul" ? "</ul>" : "</ol>"); inList = false; }
      const block = codeBlocks[parseInt(codeMatch[1])];
      result.push(`<pre class="chat-code-block"><code>${escapeHtml(block.code)}</code></pre>`);
      continue;
    }

    // Headers
    const headerMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headerMatch) {
      if (inList) { result.push(listType === "ul" ? "</ul>" : "</ol>"); inList = false; }
      const level = headerMatch[1].length;
      result.push(`<h${level} class="chat-header">${formatInline(headerMatch[2])}</h${level}>`);
      continue;
    }

    // Bullet list
    const bulletMatch = line.match(/^[-*•]\s+(.*)$/);
    if (bulletMatch) {
      if (!inList || listType !== "ul") {
        if (inList) result.push("</ol>");
        result.push('<ul class="chat-list">');
        inList = true;
        listType = "ul";
      }
      result.push(`<li>${formatInline(bulletMatch[1])}</li>`);
      continue;
    }

    // Numbered list
    const numMatch = line.match(/^\d+\.\s+(.*)$/);
    if (numMatch) {
      if (!inList || listType !== "ol") {
        if (inList) result.push("</ul>");
        result.push('<ol class="chat-numbered-list">');
        inList = true;
        listType = "ol";
      }
      result.push(`<li>${formatInline(numMatch[1])}</li>`);
      continue;
    }

    // Close list if not continuing
    if (inList) {
      result.push(listType === "ul" ? "</ul>" : "</ol>");
      inList = false;
    }

    // Empty line or regular text
    if (line.trim() === "") {
      result.push("<br>");
    } else {
      result.push(formatInline(line) + "<br>");
    }
  }

  if (inList) result.push(listType === "ul" ? "</ul>" : "</ol>");

  let html = result.join("");

  // Restore inline code
  inlineCodes.forEach((code, i) => {
    html = html.replace(`__INLINE_CODE_${i}__`, `<code class="chat-inline-code">${escapeHtml(code)}</code>`);
  });

  return html;
}

function formatInline(text) {
  if (!text) return "";
  return escapeHtml(text)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}
