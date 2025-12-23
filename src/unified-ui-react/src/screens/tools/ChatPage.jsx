import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Paperclip, Send } from "lucide-react";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import * as chatApi from "../../api/chat";
import * as filesApi from "../../api/files";

export function ChatPage() {
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [value, setValue] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [historyHydrated, setHistoryHydrated] = useState(false);

  const fileRef = useRef(null);
  const endRef = useRef(null);
  const abortRef = useRef(null);

  const historyQuery = useQuery({
    queryKey: ["chat", "history"],
    queryFn: chatApi.getHistory,
    enabled: true,
  });

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
    } else {
      setMessages([createGreeting()]);
    }
    setHistoryHydrated(true);
  }, [historyQuery.data, historyQuery.isLoading, historyHydrated]);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, streaming]);
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
            url: URL.createObjectURL(pendingFile),
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
        };
        const resolvedUrl = filesApi.resolveFileUrl(resolved);
        setMessages((prev) =>
          prev.map((mm) =>
            mm.id === userMsgId ? { ...mm, files: [{ ...resolved, url: resolvedUrl }] } : mm
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

            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId ? { ...mm, status: null, content: fullContent } : mm
              )
            );
            return;
          }

          if (evt?.content && !evt.type) {
            fullContent += evt.content;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId ? { ...mm, status: null, content: fullContent } : mm
              )
            );
            return;
          }

          if (evt?.type === "files" && evt.files) {
            filesReceived = true;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId
                  ? { ...mm, files: [...(mm.files || []), ...evt.files] }
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
            const fileData = evt.file || evt;
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
                  ? { ...mm, files: [...(mm.files || []), ...evt.files] }
                  : mm
              )
            );
            return;
          }

          if (typeof evt === "string" && evt.trim()) {
            fullContent += evt;
            setMessages((prev) =>
              prev.map((mm) =>
                mm.id === assistantMsgId ? { ...mm, status: null, content: fullContent } : mm
              )
            );
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
        <div className="h-full overflow-y-auto pr-2">
          <div className="space-y-3">
            {!historyHydrated && historyQuery.isLoading ? (
              <div className="text-sm text-black/60 dark:text-white/65">Loading conversation...</div>
            ) : null}
            {messages.map((m) => (
              <Message key={m.id} msg={m} />
            ))}
            <div ref={endRef} />
          </div>
        </div>
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

          <Textarea5 value={value} onChange={setValue} placeholder="Type your message..." onEnter={send} disabled={streaming} />

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

function Message({ msg }) {
  const isUser = msg.role === "user";
  const formatted = useMemo(() => formatContent(msg.content || ""), [msg.content]);
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={[
          "max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-soft",
          "ring-1 ring-black/5 dark:ring-white/10 backdrop-blur-xs",
          isUser
            ? "bg-black text-white dark:bg-white dark:text-black"
            : "bg-white/70 dark:bg-white/10",
        ].join(" ")}
      >
        {msg.status ? (
          <span className="opacity-75">{msg.status}</span>
        ) : (
          <div dangerouslySetInnerHTML={{ __html: formatted }} />
        )}

        {msg.files?.length ? (
          <div className="mt-2 space-y-1">
            {msg.files.map((f, i) => {
              const url = filesApi.resolveFileUrl(f);
              if (!url) return null;
              const name = f.filename || f.name || "file";
              const ext = name.split(".").pop()?.toLowerCase();
              const isImage = ["jpg", "jpeg", "png", "gif", "webp", "bmp"].includes(ext);

              if (isImage) {
                return (
                  <div key={f.file_id || url || i} className="overflow-hidden rounded-xl border border-black/5 dark:border-white/10">
                    <img
                      src={url}
                      alt={name}
                      className="max-h-64 w-full object-cover"
                      loading="lazy"
                    />
                  </div>
                );
              }

              return (
                <a
                  key={f.file_id || url || i}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-xs underline opacity-80 hover:opacity-100"
                >
                  {name}
                </a>
              );
            })}
          </div>
        ) : null}
      </div>
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

function normalizeHistoryMessage(msg) {
  return {
    id: msg.id || msg.message_id || crypto.randomUUID(),
    role: msg.role || msg.sender || "assistant",
    content: msg.content || msg.message || "",
    files: msg.files || msg.attachments || [],
    status: null,
  };
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
