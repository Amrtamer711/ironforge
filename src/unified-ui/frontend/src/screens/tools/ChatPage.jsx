import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Virtuoso } from "react-virtuoso";
import { ExternalLink, Download , FileText, Paperclip, Send } from "lucide-react";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import * as chatApi from "../../api/chat";
import * as filesApi from "../../api/files";
import { getAuthToken } from "../../lib/token";
import { useAttachmentLoader } from "../../hooks/useAttachmentLoader";

export function ChatPage() {
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [value, setValue] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [historyHydrated, setHistoryHydrated] = useState(false);
  const [attachmentFileIds, setAttachmentFileIds] = useState([]);

  const fileRef = useRef(null);
  const abortRef = useRef(null);
  const stickToBottomRef = useRef(true);

  // Streaming update batching - reduces re-renders from 11+ per chunk to 1 per frame
  const pendingUpdateRef = useRef(null);
  const rafIdRef = useRef(null);

  // Virtuoso ref for programmatic scrolling
  const virtuosoRef = useRef(null);

  const historyQuery = useQuery({
    queryKey: ["chat", "history"],
    queryFn: chatApi.getHistory,
    staleTime: 5 * 60 * 1000, // 5 minutes - avoid refetching on every mount
    refetchOnMount: false,
  });

  // Lazy attachment loading with pre-fetching
  const { urls: attachmentUrls, loadAttachments } = useAttachmentLoader(attachmentFileIds);

  const canSend = useMemo(
    () => (value.trim().length > 0 || Boolean(pendingFile)) && !streaming,
    [value, pendingFile, streaming]
  );

  useEffect(() => {
    if (historyHydrated) return;
    if (historyQuery.isLoading) return;

    const history = historyQuery.data;
    if (history && (history.messages?.length || history.session_id || history.conversation_id)) {
      setConversationId(history.session_id || history.conversation_id || null);
      const msgs = (history.messages || []).map(normalizeHistoryMessage);
      setMessages(msgs.length ? msgs : [createGreeting()]);

      // Capture attachment file IDs for lazy loading
      if (history.attachment_file_ids?.length) {
        setAttachmentFileIds(history.attachment_file_ids);
      }
    } else {
      setMessages([createGreeting()]);
    }
    setHistoryHydrated(true);
  }, [historyQuery.data, historyQuery.isLoading, historyHydrated]);

  const scrollToBottom = useCallback((behavior = "smooth", force = false) => {
    if (!force && !stickToBottomRef.current) return;
    // Use Virtuoso's scrollToIndex for smooth scrolling
    if (virtuosoRef.current) {
      virtuosoRef.current.scrollToIndex({ index: "LAST", behavior });
    }
  }, []);

  // Stable callback for media load - prevents Message re-renders
  const handleMediaLoad = useCallback(() => scrollToBottom("auto"), [scrollToBottom]);

  // Batched message update - coalesces rapid streaming updates into single RAF
  const queueMessageUpdate = useCallback((msgId, updateFn) => {
    // Store the update function keyed by message ID
    if (!pendingUpdateRef.current) {
      pendingUpdateRef.current = new Map();
    }
    pendingUpdateRef.current.set(msgId, updateFn);

    // Schedule a single RAF to flush all pending updates
    if (!rafIdRef.current) {
      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = null;
        if (!pendingUpdateRef.current || pendingUpdateRef.current.size === 0) return;

        const updates = pendingUpdateRef.current;
        pendingUpdateRef.current = null;

        setMessages((prev) =>
          prev.map((mm) => {
            const updateFn = updates.get(mm.id);
            return updateFn ? updateFn(mm) : mm;
          })
        );
      });
    }
  }, []);

  useEffect(() => {
    const behavior = streaming ? "auto" : "smooth";
    requestAnimationFrame(() => scrollToBottom(behavior));
  }, [messages, streaming, scrollToBottom]);
  useEffect(() => {
    if (historyHydrated) {
      requestAnimationFrame(() => scrollToBottom("auto", true));
    }
  }, [historyHydrated, scrollToBottom]);
  useEffect(() => () => abortRef.current?.abort?.(), []);

  async function send() {
    if (!canSend) return;

    const userText = value.trim();
    const outgoingMessage = userText || (pendingFile ? `Please process this file: ${pendingFile.name}` : "");

    const userMsgId = crypto.randomUUID();
    const userAttachment =
      pendingFile
        ? [{
            file_id: `local-${Date.now()}`,
            filename: pendingFile.name,
            preview_url: URL.createObjectURL(pendingFile),
          }]
        : [];

    const userMsg = {
      id: userMsgId,
      role: "user",
      content: userText,
      files: userAttachment,
      status: null,
    };

    const assistantMsgId = crypto.randomUUID();
    const assistantMsg = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      files: [],
      status: "Thinking...",
    };

    setMessages((m) => [...m, userMsg, assistantMsg]);
    setValue("");
    setPendingFile(null);
    stickToBottomRef.current = true;
    requestAnimationFrame(() => scrollToBottom("auto", true));

    try {
      setStreaming(true);
      abortRef.current?.abort?.();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      let fileIds = [];
      let fullContent = "";
      let currentMessageId = null;
      let filesReceived = false;

      // 1) upload file if present (same endpoint as old chat.js)
      if (pendingFile) {
        const uploaded = await filesApi.uploadFile(pendingFile);
        if (!uploaded?.file_id) throw new Error("Upload failed");

        fileIds = [uploaded.file_id];
        const resolved = {
          file_id: uploaded.file_id,
          filename: pendingFile.name,
          file_url: uploaded.file_url || uploaded.url || "",
        };
        setMessages((prev) =>
          prev.map((mm) =>
            mm.id === userMsgId
              ? {
                  ...mm,
                  files: [
                    {
                      ...resolved,
                      preview_url: mm.files?.[0]?.preview_url || mm.files?.[0]?.url || "",
                    },
                  ],
                }
              : mm
          )
        );
      }

      // 2) stream response (SSE)
      await chatApi.streamMessage({
        conversationId,
        message: outgoingMessage,
        fileIds,
        signal: ctrl.signal,
        onEvent: (evt) => {
          const pdfFilename = evt?.result?.pdf_filename || evt?.pdf_filename;
          const decorateFile = (file) => {
            if (!file) return file;
            if (!pdfFilename) return file;
            if (file.pdf_filename) return file;
            return { ...file, pdf_filename: pdfFilename };
          };
          if (pdfFilename) {
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId && !mm.pdf_filename ? { ...mm, pdf_filename: pdfFilename } : mm
              )
            );
          }
          // Mirrors old chat.js event types
          if (evt?.conversation_id) {
            setConversationId((prev) => prev || evt.conversation_id);
          }

          if (evt?.error) {
            setMessages((prev) => prev.map((mm) => (mm.id === assistantMsgId ? { ...mm, status: null, content: `Error: ${evt.error}` } : mm)));
            return;
          }

          if (evt?.type === "status") {
            setMessages((prev) => prev.map((mm) => (mm.id === assistantMsgId ? { ...mm, status: evt.content || "Processing..." } : mm)));
            if (evt.message_id) currentMessageId = evt.message_id;
            return;
          }

          if (evt?.type === "delete") {
            if (evt.message_id && evt.message_id === currentMessageId) {
              fullContent = "";
              currentMessageId = null;
              setMessages((prev) => prev.map((mm) => (mm.id === assistantMsgId ? { ...mm, status: "Thinking...", content: "" } : mm)));
            }
            return;
          }

          if (evt?.type === "tool_call") {
            const toolName = evt.tool?.name || "processing";
            setMessages((prev) => prev.map((mm) => (mm.id === assistantMsgId ? { ...mm, status: `Processing ${toolName}...` } : mm)));
            return;
          }

          if ((evt?.type === "chunk" || evt?.type === "content") && evt.content) {
            if (evt.message_id && evt.message_id !== currentMessageId) currentMessageId = evt.message_id;
            fullContent = evt.type === "content" ? evt.content : fullContent + evt.content;

            // Use batched update for high-frequency chunk events
            const capturedContent = fullContent;
            queueMessageUpdate(assistantMsgId, (mm) => ({ ...mm, status: null, content: capturedContent }));
            return;
          }

          if (evt?.content && !evt.type) {
            fullContent += evt.content;
            // Use batched update for high-frequency chunk events
            const capturedContent = fullContent;
            queueMessageUpdate(assistantMsgId, (mm) => ({ ...mm, status: null, content: capturedContent }));
            return;
          }

          if (evt?.type === "files" && evt.files) {
            filesReceived = true;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId
                  ? { ...mm, files: [...(mm.files || []), ...evt.files.map(decorateFile)] }
                  : mm
              )
            );
            if (!fullContent) {
              const withComment = evt.files.find((f) => f.comment);
              if (withComment?.comment) {
                fullContent = withComment.comment;
                setMessages((prev) =>
                  prev.map((mm) =>
                    mm.id === assistantMsgId ? { ...mm, status: null, content: fullContent } : mm
                  )
                );
              }
            }
            return;
          }

          if (evt?.type === "file" && (evt.file || evt.url)) {
            const fileData = decorateFile(evt.file || evt);
            filesReceived = true;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId
                  ? { ...mm, files: [...(mm.files || []), fileData] }
                  : mm
              )
            );
            if (!fullContent && fileData.comment) {
              fullContent = fileData.comment;
              setMessages((prev) =>
                prev.map((mm) =>
                  mm.id === assistantMsgId ? { ...mm, status: null, content: fullContent } : mm
                )
              );
            }
            return;
          }

          if (evt?.files) {
            filesReceived = true;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId
                  ? { ...mm, files: [...(mm.files || []), ...evt.files.map(decorateFile)] }
                  : mm
              )
            );
            return;
          }

          if (typeof evt === "string" && evt.trim()) {
            fullContent += evt;
            // Use batched update for string content
            const capturedContent = fullContent;
            queueMessageUpdate(assistantMsgId, (mm) => ({ ...mm, status: null, content: capturedContent }));
          }
        },
        onDone: () => {
          if (!fullContent && !filesReceived) {
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId
                  ? { ...mm, status: null, content: "I'm ready to help. What would you like to do?" }
                  : mm
              )
            );
          }
        },
      });
    } catch (e) {
      setMessages((prev) =>
        prev.map((mm) =>
          mm.id === assistantMsgId
            ? { ...mm, status: null, content: e?.message || "Failed to get response" }
            : mm
        )
      );
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="h-full flex flex-col gap-4 min-h-0">
      <Card className="p-4 overflow-hidden flex-1 min-h-0">
        {!historyHydrated && historyQuery.isLoading ? (
          <div className="h-full flex items-center justify-center">
            <LoadingEllipsis
              text="Loading conversation"
              className="text-sm text-black/60 dark:text-white/65"
            />
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            className="h-full scrollbar-thin"
            data={messages}
            followOutput="smooth"
            atBottomStateChange={(atBottom) => {
              stickToBottomRef.current = atBottom;
            }}
            itemContent={(index, msg) => (
              <div className="px-2 py-1.5">
                <Message
                  msg={msg}
                  attachmentUrls={attachmentUrls}
                  onAttachmentVisible={loadAttachments}
                  onMediaLoad={handleMediaLoad}
                />
              </div>
            )}
          />
        )}
      </Card>

      <Card className="p-3">
        {pendingFile ? (
          <div className="mb-2 flex items-center justify-between rounded-2xl bg-black/5 dark:bg-white/10 px-3 py-2 text-sm">
            <div className="truncate">{pendingFile.name}</div>
            <button className="opacity-70 hover:opacity-100" onClick={() => setPendingFile(null)}>✕</button>
          </div>
        ) : null}

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

          <Textarea5 value={value} onChange={setValue} placeholder="Type your message..." onEnter={send} />

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

const Message = React.memo(function Message({ msg, attachmentUrls = {}, onAttachmentVisible, onMediaLoad }) {
  const isUser = msg.role === "user";
  const formatted = useMemo(() => formatContent(msg.content || ""), [msg.content]);
  const statusText = useMemo(() => normalizeStatusText(msg.status || ""), [msg.status]);
  const isStatusContent = useMemo(
    () => !msg.status && isStatusOnlyContent(msg.content || ""),
    [msg.status, msg.content]
  );
  const fallbackStatus = useMemo(() => normalizeStatusText(msg.content || ""), [msg.content]);
  const nameCacheRef = useRef(new Map());
  const attachmentRef = useRef(null);
  const observedRef = useRef(false);

  // Intersection Observer for lazy loading attachments
  useEffect(() => {
    if (!msg.files?.length || observedRef.current) return;

    const el = attachmentRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !observedRef.current) {
            observedRef.current = true;
            // Collect file_ids from this message's attachments
            const fileIds = msg.files.map((f) => f.file_id).filter(Boolean);
            if (fileIds.length && onAttachmentVisible) {
              onAttachmentVisible(fileIds);
            }
            observer.disconnect();
          }
        });
      },
      { rootMargin: "200px" } // Pre-load when 200px away from viewport
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [msg.files, onAttachmentVisible]);

  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={[
          "max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-soft break-words",
          "ring-1 ring-black/5 dark:ring-white/10 backdrop-blur-xs",
          isUser
            ? "bg-black text-white dark:bg-white dark:text-black"
            : "bg-white/70 dark:bg-white/10",
        ].join(" ")}
      >
        {msg.status || isStatusContent ? (
          <StatusLine text={statusText || fallbackStatus} />
        ) : (
          <div dangerouslySetInnerHTML={{ __html: formatted }} />
        )}

        {msg.files?.length ? (
          <div ref={attachmentRef} className="mt-2 space-y-1">
            {msg.files.map((f, i) => {
              // Check for refreshed URL first, then fallback to resolveFileUrl
              const refreshedUrl = f.file_id ? attachmentUrls[f.file_id] : null;
              const url = refreshedUrl || filesApi.resolveFileUrl(f);
              if (!url) return null;
              const resolvedPdfFilename = f.pdf_filename || msg.pdf_filename;
              const displayName = getFriendlyFileName(
                resolvedPdfFilename ? { ...f, pdf_filename: resolvedPdfFilename } : f,
                url,
                nameCacheRef.current
              );
              const ext = getFileExtension(displayName);
              const isImage = ["jpg", "jpeg", "png", "gif", "webp", "bmp"].includes(ext);
              const showActions = !isUser;
              const isPdf = ext === "pdf";

              if (isImage) {
                return (
                  <div
                    key={f.file_id || url || i}
                    className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-2"
                  >
                    {showActions ? (
                      <>
                        <a href={url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-lg">
                          <img
                            src={url}
                            alt={displayName}
                            className="max-h-64 w-full object-cover"
                            loading="lazy"
                            onLoad={onMediaLoad}
                          />
                        </a>
                        <div className="mt-2 flex items-center gap-2">
                          <Button
                            asChild
                            size="sm"
                            variant="ghost"
                            className="rounded-xl"
                          >
                            <a href={url} target="_blank" rel="noopener noreferrer">
                              <ExternalLink size={14} className="mr-1" />
                              Open
                            </a>
                          </Button>
                          <Button size="sm" variant="secondary" className="rounded-xl">
                            <span
                              role="link"
                              tabIndex={0}
                              onClick={(e) => {
                                e.preventDefault();
                                downloadFile(url, displayName);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  downloadFile(url, displayName);
                                }
                              }}
                              className="inline-flex items-center"
                            >
                              <Download size={14} className="mr-1" />
                              Download
                            </span>
                          </Button>
                        </div>
                      </>
                    ) : (
                      <div className="overflow-hidden rounded-lg">
                        <img
                          src={url}
                          alt={displayName}
                          className="max-h-64 w-full object-cover"
                          loading="lazy"
                          onLoad={onMediaLoad}
                        />
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div
                  key={f.file_id || url || i}
                  className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-black/50 dark:text-white/60">
                        {isPdf ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-0.5">
                            <FileText size={12} />
                            PDF
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-full bg-black/5 dark:bg-white/10 px-2 py-0.5">
                            {ext ? ext.toUpperCase() : "FILE"}
                          </span>
                        )}
                      </div>
                      {showActions ? (
                        <div className="mt-1 text-xs font-semibold text-black/80 dark:text-white/85 truncate">
                          {displayName}
                        </div>
                      ) : null}
                    </div>
                    {showActions ? (
                      <div className="flex items-center gap-2">
                        <Button
                          asChild
                          size="sm"
                          variant="ghost"
                          className="rounded-xl"
                        >
                          <a href={url} target="_blank" rel="noopener noreferrer">
                            <ExternalLink size={14} className="mr-1" />
                            Open
                          </a>
                        </Button>
                        <Button size="sm" variant="secondary" className="rounded-xl">
                          <span
                            role="link"
                            tabIndex={0}
                            onClick={(e) => {
                              e.preventDefault();
                              downloadFile(url, displayName);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                downloadFile(url, displayName);
                              }
                            }}
                            className="inline-flex items-center"
                          >
                            <Download size={14} className="mr-1" />
                            Download
                          </span>
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
});

function Textarea5({ value, onChange, placeholder, onEnter, disabled }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    const lineHeight = 22;
    const max = lineHeight * 5 + 16;
    el.style.height = Math.min(el.scrollHeight, max) + "px";
  }, [value]);

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onEnter?.();
    }
  }

  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      className="w-full resize-none rounded-2xl bg-white/60 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-black/10 dark:focus:ring-white/15 overflow-auto"
      style={{ maxHeight: "132px" }}
    />
  );
}

function StatusLine({ text }) {
  return (
    <span className="inline-flex items-center gap-2 opacity-80">
      <span>{text || "Thinking"}</span>
      <span className="mmg-ellipsis" aria-hidden="true">
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "0ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "120ms" }} />
        <span className="mmg-ellipsis-dot" style={{ animationDelay: "240ms" }} />
      </span>
    </span>
  );
}

function normalizeHistoryMessage(msg) {
  return {
    id: msg.id || msg.message_id || crypto.randomUUID(),
    role: msg.role || msg.sender || "assistant",
    content: msg.content || msg.message || "",
    files: msg.files || msg.attachments || [],
    status: null,
  };
}

function normalizeStatusText(text) {
  if (!text) return "";
  return String(text)
    .replace(/[⏳⌛]/g, "")
    .replace(/[_*`]/g, "")
    .replace(/\.+$/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isStatusOnlyContent(content) {
  const cleaned = normalizeStatusText(content);
  if (!cleaned) return false;
  if (cleaned === "Thinking") return true;
  if (cleaned.startsWith("Processing")) return true;
  if (cleaned.startsWith("Building Proposal")) return true;
  return false;
}

function getFileExtension(value) {
  if (!value) return "";
  const cleaned = String(value).split("?")[0].split("#")[0];
  const parts = cleaned.split(".");
  if (parts.length <= 1) return "";
  return parts.pop().toLowerCase();
}

function getNameFromUrl(url) {
  if (!url) return "";
  try {
    const resolved = new URL(url, window.location.href);
    const parts = resolved.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  } catch {
    const fallback = url.split("?")[0].split("#")[0];
    const parts = fallback.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  }
}

function isGenericFileName(name) {
  if (!name) return true;
  const lower = name.trim().toLowerCase();
  if (!lower) return true;
  if (lower === "file" || lower === "download") return true;
  const base = lower.replace(/\.[^.]+$/, "");
  if (base === "tmp" || base === "temp") return true;
  if (/^[a-f0-9-]{16,}$/.test(base)) return true;
  if (/^file[-_]?\d+$/.test(base)) return true;
  if (/^(tmp|temp)/.test(base)) return true;
  if (/^upload[-_]?.+$/.test(base)) return true;
  return false;
}

function getFriendlyFileName(file, url, cache) {
  const pdfFilename = file?.filename || "";
  const raw = pdfFilename || file?.filename || file?.title || "";
  const urlName = getNameFromUrl(url);
  const key = file?.file_id || file?.id || url || raw;
  let name = raw || urlName || "";
  const ext = getFileExtension(name) || getFileExtension(urlName) || getFileExtension(url);

  if (pdfFilename) {
    const pdfExt = getFileExtension(name) || "pdf";
    if (!name.toLowerCase().endsWith(`.${pdfExt}`)) {
      name = `${name}.${pdfExt}`;
    }
    return name;
  }

  if (isGenericFileName(name)) {
    if (ext === "pdf") {
      name = `Proposal.pdf`;
    } else if (ext) {
      name = `Attachment.${ext}`;
    } else {
      name = "Attachment";
    }
  } else if (ext && !name.toLowerCase().endsWith(`.${ext}`)) {
    name = `${name}.${ext}`;
  }

  return name || (ext ? `Attachment.${ext}` : "Attachment");
}

async function downloadFile(url, filename) {
  try {
    const token = getAuthToken();
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
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
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
}

function formatDateTime(value) {
  const date = value ? new Date(value) : new Date();
  const safe = Number.isNaN(date.getTime()) ? new Date() : date;
  const pad = (num) => String(num).padStart(2, "0");
  const datePart = [safe.getFullYear(), pad(safe.getMonth() + 1), pad(safe.getDate())].join("-");
  const timePart = [pad(safe.getHours()), pad(safe.getMinutes()), pad(safe.getSeconds())].join("");
  return `${datePart}_${timePart}`;
}

function createGreeting() {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: `Good ${greetingByTime()}, how can I help?`,
    files: [],
    status: null,
  };
}

function greetingByTime() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInline(text) {
  if (!text) return "";
  const safe = escapeHtml(text);

  return safe
    // Links: [text](url)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>')
    // Images: ![alt](url) - render as linked text since we can't embed arbitrary images
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-link">[Image: $1]</a>')
    // Bold + Italic: ***text*** or ___text___
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/___(.+?)___/g, "<strong><em>$1</em></strong>")
    // Bold: **text** or __text__
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(?!INLINE_CODE_|CODE_BLOCK_)(.+?)__/g, "<strong>$1</strong>")
    // Italic: *text* or _text_
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
    .replace(/(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)/g, "<em>$1</em>")
    // Strikethrough: ~~text~~
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    // Highlight/mark: ==text==
    .replace(/==(.+?)==/g, '<mark class="chat-highlight">$1</mark>');
}

function formatContent(content) {
  if (!content) return "";

  // Step 1: Extract and protect code blocks (``` ... ```)
  const codeBlocks = [];
  let processed = content.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const index = codeBlocks.length;
    codeBlocks.push({ lang: lang || "", code: code.trim() });
    return `__CODE_BLOCK_${index}__`;
  });

  // Step 2: Extract and protect inline code (` ... `)
  const inlineCodes = [];
  processed = processed.replace(/`([^`]+)`/g, (_, code) => {
    const index = inlineCodes.length;
    inlineCodes.push(code);
    return `__INLINE_CODE_${index}__`;
  });

  // Step 3: Process line by line
  const lines = processed.split("\n");
  let result = [];
  let inBulletList = false;
  let inNumberedList = false;
  let inBlockquote = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Check for code block placeholder
    const codeBlockMatch = line.match(/^__CODE_BLOCK_(\d+)__$/);
    if (codeBlockMatch) {
      if (inBulletList) { result.push("</ul>"); inBulletList = false; }
      if (inNumberedList) { result.push("</ol>"); inNumberedList = false; }
      if (inBlockquote) { result.push("</blockquote>"); inBlockquote = false; }

      const block = codeBlocks[parseInt(codeBlockMatch[1])];
      const langClass = block.lang ? ` class="language-${block.lang}"` : "";
      result.push(`<pre class="chat-code-block"><code${langClass}>${escapeHtml(block.code)}</code></pre>`);
      continue;
    }

    // Check for headers (# ## ### etc)
    const headerMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headerMatch) {
      if (inBulletList) { result.push("</ul>"); inBulletList = false; }
      if (inNumberedList) { result.push("</ol>"); inNumberedList = false; }
      if (inBlockquote) { result.push("</blockquote>"); inBlockquote = false; }

      const level = headerMatch[1].length;
      const text = formatInline(headerMatch[2]);
      result.push(`<h${level} class="chat-header chat-h${level}">${text}</h${level}>`);
      continue;
    }

    // Check for horizontal rule (---, ***, ___)
    if (/^[-*_]{3,}\s*$/.test(line)) {
      if (inBulletList) { result.push("</ul>"); inBulletList = false; }
      if (inNumberedList) { result.push("</ol>"); inNumberedList = false; }
      if (inBlockquote) { result.push("</blockquote>"); inBlockquote = false; }
      result.push('<hr class="chat-hr">');
      continue;
    }

    // Check for blockquote (> text)
    const blockquoteMatch = line.match(/^>\s*(.*)$/);
    if (blockquoteMatch) {
      if (inBulletList) { result.push("</ul>"); inBulletList = false; }
      if (inNumberedList) { result.push("</ol>"); inNumberedList = false; }

      if (!inBlockquote) {
        result.push('<blockquote class="chat-blockquote">');
        inBlockquote = true;
      }
      result.push(formatInline(blockquoteMatch[1]) + "<br>");
      continue;
    } else if (inBlockquote) {
      result.push("</blockquote>");
      inBlockquote = false;
    }

    // Check for bullet list (-, *, •)
    const bulletMatch = line.match(/^(\s*)([-*•])\s+(.*)$/);
    if (bulletMatch) {
      if (inNumberedList) { result.push("</ol>"); inNumberedList = false; }

      if (!inBulletList) {
        result.push('<ul class="chat-list">');
        inBulletList = true;
      }
      const text = formatInline(bulletMatch[3]);
      result.push(`<li>${text}</li>`);
      continue;
    } else if (inBulletList) {
      result.push("</ul>");
      inBulletList = false;
    }

    // Check for numbered list (1. 2. etc)
    const numberedMatch = line.match(/^(\s*)(\d+)\.\s+(.*)$/);
    if (numberedMatch) {
      if (inBulletList) { result.push("</ul>"); inBulletList = false; }

      if (!inNumberedList) {
        result.push('<ol class="chat-numbered-list">');
        inNumberedList = true;
      }
      const text = formatInline(numberedMatch[3]);
      result.push(`<li>${text}</li>`);
      continue;
    } else if (inNumberedList) {
      result.push("</ol>");
      inNumberedList = false;
    }

    // Empty line
    if (line.trim() === "") {
      result.push("<br>");
      continue;
    }

    result.push(formatInline(line));
    if (i < lines.length - 1) {
      result.push("<br>");
    }
  }

  if (inBulletList) result.push("</ul>");
  if (inNumberedList) result.push("</ol>");
  if (inBlockquote) result.push("</blockquote>");

  let html = result.join("");

  inlineCodes.forEach((code, index) => {
    html = html.replace(`__INLINE_CODE_${index}__`, `<code class="chat-inline-code">${escapeHtml(code)}</code>`);
  });

  return html;
}
