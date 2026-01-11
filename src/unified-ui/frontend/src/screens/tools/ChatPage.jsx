import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Virtuoso } from "react-virtuoso";
import { ExternalLink, Download, FileText, ImageIcon, Loader2, Paperclip, Send } from "lucide-react";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { LoadingEllipsis } from "../../components/ui/loading-ellipsis";
import * as chatApi from "../../api/chat";
import * as filesApi from "../../api/files";
import { getAuthToken } from "../../lib/token";
import { useAttachmentLoader } from "../../hooks/useAttachmentLoader";
import { useImagePrefetch } from "../../hooks/useImagePrefetch";

// Pagination config
const PAGE_SIZE = 50;

export function ChatPage() {
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [value, setValue] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [attachmentFileIds, setAttachmentFileIds] = useState([]);

  // Pagination state
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyHydrated, setHistoryHydrated] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const offsetRef = useRef(0); // Track how many messages we've loaded from the end

  const fileRef = useRef(null);
  const abortRef = useRef(null);
  const paginationAbortRef = useRef(null); // Abort controller for pagination requests
  const stickToBottomRef = useRef(true);

  // Streaming update batching - reduces re-renders from 11+ per chunk to 1 per frame
  const pendingUpdateRef = useRef(null);
  const rafIdRef = useRef(null);

  // Virtuoso ref for programmatic scrolling
  const virtuosoRef = useRef(null);

  // Initial history load - fetch last PAGE_SIZE messages
  useEffect(() => {
    if (historyHydrated) return;

    async function loadInitialHistory() {
      try {
        setHistoryLoading(true);
        const history = await chatApi.getHistory({
          limit: PAGE_SIZE,
          offset: 0,
          newestFirst: true,
        });

        if (history && (history.messages?.length || history.session_id || history.conversation_id)) {
          setConversationId(history.session_id || history.conversation_id || null);
          const msgs = (history.messages || []).map(normalizeHistoryMessage);
          setMessages(msgs.length ? msgs : [createGreeting()]);
          setHasMore(history.has_more || false);
          offsetRef.current = msgs.length;

          // Capture attachment file IDs for lazy loading
          if (history.attachment_file_ids?.length) {
            setAttachmentFileIds(history.attachment_file_ids);
          }
        } else {
          setMessages([createGreeting()]);
          setHasMore(false);
        }
      } catch (err) {
        console.error("[ChatPage] Failed to load history:", err);
        setMessages([createGreeting()]);
        setHasMore(false);
      } finally {
        setHistoryLoading(false);
        setHistoryHydrated(true);
      }
    }

    loadInitialHistory();
  }, [historyHydrated]);

  // Lazy attachment loading with pre-fetching
  const { urls: attachmentUrls, loadAttachments } = useAttachmentLoader(attachmentFileIds);

  // Ensure ALL messages' file IDs are tracked for URL resolution
  useEffect(() => {
    const allFileIds = messages.flatMap(m =>
      m.files?.map(f => f.file_id).filter(Boolean) || []
    );

    // Only update if the set of file IDs actually changed
    setAttachmentFileIds(prev => {
      const prevSet = new Set(prev);
      const newSet = new Set(allFileIds);
      if (prevSet.size === newSet.size && [...prevSet].every(id => newSet.has(id))) {
        return prev; // No change
      }
      return allFileIds;
    });
  }, [messages]);

  // Initial preload: Load last 50 messages' images immediately
  useEffect(() => {
    if (!historyHydrated || messages.length === 0) return;

    // Get last 50 messages' file IDs
    const last50 = messages.slice(-50);
    const fileIds = last50.flatMap(m =>
      m.files?.map(f => f.file_id).filter(Boolean) || []
    );

    if (fileIds.length > 0) {
      // Aggressively load all URLs for last 50 messages
      console.log(`[ChatPage] Preloading ${fileIds.length} images from last 50 messages`);
      loadAttachments(fileIds);
    }
  }, [historyHydrated, messages, loadAttachments]);

  // Prefetch next page of images
  const prefetchUrls = useMemo(() => {
    // Calculate next page to prefetch
    const lastVisibleIdx = messages.length - 1;
    const currentPage = Math.floor(lastVisibleIdx / PAGE_SIZE);
    const nextPageStart = (currentPage + 1) * PAGE_SIZE;
    const nextPageEnd = nextPageStart + PAGE_SIZE;

    const nextPageMessages = messages.slice(nextPageStart, nextPageEnd);

    return nextPageMessages.flatMap(m =>
      m.files?.map(f => ({
        fileId: f.file_id,
        thumbnailUrl: attachmentUrls[f.file_id]?.thumbnail,
        fullUrl: attachmentUrls[f.file_id]?.full
      })).filter(item => item.fileId && (item.thumbnailUrl || item.fullUrl)) || []
    );
  }, [messages, attachmentUrls]);

  // Activate prefetch system
  useImagePrefetch(prefetchUrls);

  const canSend = useMemo(
    () => (value.trim().length > 0 || Boolean(pendingFile)) && !streaming,
    [value, pendingFile, streaming]
  );

  // Load older messages when scrolling to top
  const loadOlderMessages = useCallback(async () => {
    if (loadingMore || !hasMore) return;

    // Abort previous pagination request if still running
    paginationAbortRef.current?.abort();
    const ctrl = new AbortController();
    paginationAbortRef.current = ctrl;

    try {
      setLoadingMore(true);
      const history = await chatApi.getHistory({
        limit: PAGE_SIZE,
        offset: offsetRef.current,
        newestFirst: true,
        signal: ctrl.signal, // Pass abort signal to API
      });

      // Check if aborted before updating state
      if (ctrl.signal.aborted) return;

      if (history?.messages?.length) {
        const olderMsgs = history.messages.map(normalizeHistoryMessage);
        // Prepend older messages
        setMessages((prev) => [...olderMsgs, ...prev]);
        setHasMore(history.has_more || false);
        offsetRef.current += olderMsgs.length;

        // Accumulate attachment file IDs
        if (history.attachment_file_ids?.length) {
          setAttachmentFileIds((prev) => [...history.attachment_file_ids, ...prev]);
        }
      } else {
        setHasMore(false);
      }
    } catch (err) {
      // Ignore abort errors
      if (err.name === 'AbortError') return;
      console.error("[ChatPage] Failed to load older messages:", err);
    } finally {
      if (!ctrl.signal.aborted) {
        setLoadingMore(false);
      }
    }
  }, [loadingMore, hasMore]);

  const scrollToBottom = useCallback((behavior = "smooth", force = false) => {
    if (!force && !stickToBottomRef.current) return;
    // Use Virtuoso's scrollToIndex for smooth scrolling
    if (virtuosoRef.current) {
      virtuosoRef.current.scrollToIndex({ index: "LAST", behavior });
    }
  }, []);

  // Stable callback for media load - prevents Message re-renders
  const handleMediaLoad = useCallback(() => scrollToBottom("auto"), [scrollToBottom]);

  // Create stable callback wrappers using refs to prevent Message re-renders
  const loadAttachmentsRef = useRef();
  loadAttachmentsRef.current = loadAttachments;
  const stableLoadAttachments = useCallback((fileIds) => {
    loadAttachmentsRef.current?.(fileIds);
  }, []); // No dependencies - stable reference

  const handleMediaLoadRef = useRef();
  handleMediaLoadRef.current = handleMediaLoad;
  const stableHandleMediaLoad = useCallback(() => {
    handleMediaLoadRef.current?.();
  }, []); // No dependencies - stable reference

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

  // Consolidated scroll trigger - prevents duplicate scroll effects
  const scrollTrigger = useMemo(() => ({
    messagesLength: messages.length,
    historyHydrated,
    lastMessageId: messages[messages.length - 1]?.id,
    streaming
  }), [messages, historyHydrated, streaming]);

  useEffect(() => {
    // Only scroll if at bottom or if history just loaded
    if (stickToBottomRef.current || historyHydrated) {
      const behavior = streaming ? "auto" : "smooth";
      const force = historyHydrated && !stickToBottomRef.current;
      requestAnimationFrame(() => scrollToBottom(behavior, force));
    }
  }, [scrollTrigger, scrollToBottom, streaming, historyHydrated]);

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
          // Guard against events firing after abort
          if (ctrl.signal.aborted) return;

          const pdfFilename = evt?.result?.pdf_filename || evt?.pdf_filename;
          const decorateFile = (file) => {
            if (!file) return file;
            if (!pdfFilename) return file;
            if (file.pdf_filename) return file;
            return { ...file, pdf_filename: pdfFilename };
          };
          if (pdfFilename) {
            queueMessageUpdate(assistantMsgId, (mm) =>
              !mm.pdf_filename ? { ...mm, pdf_filename: pdfFilename } : mm
            );
          }
          // Mirrors old chat.js event types
          if (evt?.conversation_id) {
            setConversationId((prev) => prev || evt.conversation_id);
          }

          if (evt?.error) {
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              status: null,
              content: `Error: ${evt.error}`
            }));
            return;
          }

          if (evt?.type === "status") {
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              status: evt.content || "Processing..."
            }));
            if (evt.message_id) currentMessageId = evt.message_id;
            return;
          }

          if (evt?.type === "delete") {
            if (evt.message_id && evt.message_id === currentMessageId) {
              fullContent = "";
              currentMessageId = null;
              queueMessageUpdate(assistantMsgId, (mm) => ({
                ...mm,
                status: "Thinking...",
                content: ""
              }));
            }
            return;
          }

          if (evt?.type === "tool_call") {
            const toolName = evt.tool?.name || "processing";
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              status: `Processing ${toolName}...`
            }));
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
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              files: [...(mm.files || []), ...evt.files.map(decorateFile)]
            }));
            if (!fullContent) {
              const withComment = evt.files.find((f) => f.comment);
              if (withComment?.comment) {
                fullContent = withComment.comment;
                queueMessageUpdate(assistantMsgId, (mm) => ({
                  ...mm,
                  status: null,
                  content: fullContent
                }));
              }
            }
            return;
          }

          if (evt?.type === "file" && (evt.file || evt.url)) {
            const fileData = decorateFile(evt.file || evt);
            filesReceived = true;
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              files: [...(mm.files || []), fileData]
            }));
            if (!fullContent && fileData.comment) {
              fullContent = fileData.comment;
              queueMessageUpdate(assistantMsgId, (mm) => ({
                ...mm,
                status: null,
                content: fullContent
              }));
            }
            return;
          }

          if (evt?.files) {
            filesReceived = true;
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              files: [...(mm.files || []), ...evt.files.map(decorateFile)]
            }));
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
            queueMessageUpdate(assistantMsgId, (mm) => ({
              ...mm,
              status: null,
              content: "I'm ready to help. What would you like to do?"
            }));
          }
        },
      });
    } catch (e) {
      queueMessageUpdate(assistantMsgId, (mm) => ({
        ...mm,
        status: null,
        content: e?.message || "Failed to get response"
      }));
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="h-full flex flex-col gap-4 min-h-0">
      <Card className="p-4 overflow-hidden flex-1 min-h-0">
        {historyLoading ? (
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
            followOutput={(isAtBottom) => {
              // Auto-scroll only if user is at bottom or streaming
              return (isAtBottom || streaming) ? 'smooth' : false;
            }}
            firstItemIndex={hasMore ? 1000000 - messages.length : 0}
            startReached={loadOlderMessages}
            atBottomStateChange={(atBottom) => {
              stickToBottomRef.current = atBottom;
            }}
            components={{
              Header: () =>
                loadingMore ? (
                  <div className="flex justify-center py-3">
                    <LoadingEllipsis
                      text="Loading older messages"
                      className="text-xs text-black/50 dark:text-white/50"
                    />
                  </div>
                ) : null,
            }}
            itemContent={(index, msg) => (
              <div className="px-2 py-1.5">
                <Message
                  msg={msg}
                  attachmentUrls={attachmentUrls}
                  onAttachmentVisible={stableLoadAttachments}
                  onMediaLoad={stableHandleMediaLoad}
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

  // Generate stable key for file attachments (avoid index fallback)
  const getFileKey = (file, index) => {
    return file.file_id || `${msg.id}-file-${index}`;
  };

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
              // Single source of truth for URLs:
              // 1. For files with file_id: use signed URL from attachmentUrls (required for Supabase)
              // 2. For local files (no file_id): use resolveFileUrl for blob URLs
              const urlData = f.file_id
                ? attachmentUrls[f.file_id] // Object with {thumbnail, full, width, height}
                : null;

              // For remote files (with file_id), MUST wait for signed URLs
              // Using API endpoint URLs directly fails with 401 (no auth in browser requests)
              if (f.file_id && !urlData?.full) {
                // Show placeholder while waiting for signed URL
                return (
                  <div key={getFileKey(f, i)} className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-2">
                    <div className="relative" style={{ aspectRatio: '16 / 9', width: '100%', maxWidth: '512px' }}>
                      <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/5 dark:bg-white/5 rounded-lg">
                        <Loader2 size={24} className="animate-spin text-black/30 dark:text-white/30" />
                        <span className="mt-2 text-xs text-black/50 dark:text-white/50">Loading...</span>
                      </div>
                    </div>
                  </div>
                );
              }

              const url = urlData?.full || filesApi.resolveFileUrl(f); // Fallback for local files only
              if (!url) return null; // Don't render until URL available
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
                    key={getFileKey(f, i)}
                    className="rounded-xl border border-black/5 dark:border-white/10 bg-white/70 dark:bg-white/5 p-2"
                  >
                    {showActions ? (
                      <>
                        <a href={url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-lg">
                          <ImageWithPlaceholder
                            fileId={f.file_id}
                            urlData={urlData}
                            alt={displayName}
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
                        <ImageWithPlaceholder
                          fileId={f.file_id}
                          urlData={urlData}
                          alt={displayName}
                          onLoad={onMediaLoad}
                        />
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div
                  key={getFileKey(f, i)}
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
}, (prevProps, nextProps) => {
  // Custom memo comparison to prevent unnecessary re-renders
  // Return true to SKIP re-render, false to re-render

  // Always re-render if msg object reference changed (content, status, files updated)
  if (prevProps.msg !== nextProps.msg) return false;

  // Check if attachment URLs for THIS message's files changed
  const prevUrls = prevProps.msg.files?.map(f => prevProps.attachmentUrls[f.file_id]) || [];
  const nextUrls = nextProps.msg.files?.map(f => nextProps.attachmentUrls[f.file_id]) || [];

  // Compare URL arrays
  if (prevUrls.length !== nextUrls.length) return false;
  for (let i = 0; i < prevUrls.length; i++) {
    if (prevUrls[i] !== nextUrls[i]) return false;
  }

  // Callbacks are stabilized via refs, so we can ignore them
  // Skip re-render if message and relevant URLs haven't changed
  return true;
});

/**
 * Image component with placeholder to prevent layout shifts.
 * Shows a fixed-height loading state until the image loads.
 */
function ImageWithPlaceholder({ fileId, urlData, alt, onLoad, className = "" }) {
  const [currentUrl, setCurrentUrl] = useState(null);
  const [loadState, setLoadState] = useState('loading'); // loading, thumbnail, full
  const [error, setError] = useState(false);
  const fullImgRef = useRef(null);

  const thumbnailUrl = urlData?.thumbnail;
  const fullUrl = urlData?.full;
  const aspectRatio = urlData?.width && urlData?.height
    ? `${urlData.width} / ${urlData.height}`
    : '16 / 9';

  useEffect(() => {
    if (!thumbnailUrl && !fullUrl) {
      setLoadState('loading');
      return;
    }

    // Phase 1: Load thumbnail immediately
    if (thumbnailUrl) {
      setCurrentUrl(thumbnailUrl);
      setLoadState('thumbnail');

      // Phase 2: Preload full image in background
      if (fullUrl) {
        const img = new Image();
        img.onload = () => {
          fullImgRef.current = fullUrl;
          // Swap to full image after loaded
          setTimeout(() => {
            setCurrentUrl(fullUrl);
            setLoadState('full');
          }, 100);
        };
        img.src = fullUrl;
      }
    } else if (fullUrl) {
      // No thumbnail available, load full directly
      setCurrentUrl(fullUrl);
      setLoadState('full');
    }
  }, [thumbnailUrl, fullUrl]);

  const handleLoad = useCallback(() => {
    onLoad?.();
  }, [onLoad]);

  const handleError = useCallback(() => {
    setError(true);
    setLoadState('error');
  }, []);

  return (
    <div
      className={`relative ${className}`}
      style={{
        aspectRatio,
        width: '100%',
        maxWidth: '512px'
      }}
    >
      {/* Loading placeholder */}
      {loadState === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/5 dark:bg-white/5 rounded-lg">
          <Loader2 size={24} className="animate-spin text-black/30 dark:text-white/30" />
          <span className="mt-2 text-xs text-black/50 dark:text-white/50">Loading image...</span>
        </div>
      )}

      {/* Thumbnail indicator */}
      {loadState === 'thumbnail' && (
        <div className="absolute top-2 right-2 z-10 bg-black/50 text-white text-xs px-2 py-1 rounded">
          HD Loading...
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-red-50 dark:bg-red-900/20 rounded-lg">
          <ImageIcon className="text-red-500" size={32} />
          <span className="mt-2 text-sm text-red-600 dark:text-red-400">Failed to load</span>
        </div>
      )}

      {/* Actual image */}
      {!error && currentUrl && (
        <img
          src={currentUrl}
          alt={alt}
          className={`w-full h-full object-contain rounded-lg transition-opacity duration-300 ${
            loadState === 'loading' ? 'opacity-0' : 'opacity-100'
          }`}
          loading="lazy"
          onLoad={handleLoad}
          onError={handleError}
        />
      )}
    </div>
  );
}

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
