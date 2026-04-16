import React, { useState, useEffect, useRef, useCallback } from "react";
import { sendMessage, getChatHistory, resetChat, getPendingNotifications, getConnectionState } from "../apiClient";
import ThinkingBlock from "./ThinkingBlock";
import ToolStatus from "./ToolStatus";
import TokenBar from "./TokenBar";
import InputToolbar from "./InputToolbar";
import ArtifactsPanel from "./ArtifactsPanel";
import ModelSidebar from "./ModelSidebar";

// ── Artifact detection ───────────────────────────────────────────────────────
const ARTIFACT_LINE_THRESHOLD = 20;

function extractArtifacts(text) {
  const artifacts = [];
  const codeBlockRe = /```(\w*)\n([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRe.exec(text)) !== null) {
    const lang = match[1] || "";
    const code = match[2];
    if (code.split("\n").length >= ARTIFACT_LINE_THRESHOLD) {
      artifacts.push({
        id: `art-${Date.now()}-${artifacts.length}`,
        language: lang,
        code,
        label: lang || `Block ${artifacts.length + 1}`,
      });
    }
  }
  return artifacts;
}

// ── Text highlighting for search ─────────────────────────────────────────────
function highlightText(text, query, isActive) {
  if (!query || !text) return text;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  let matchIdx = 0;
  return parts.map((part, i) => {
    if (part.toLowerCase() === query.toLowerCase()) {
      const cls = isActive && matchIdx++ === 0 ? "search-highlight active" : "search-highlight";
      return <mark key={i} className={cls}>{part}</mark>;
    }
    return part;
  });
}

// ── localStorage helpers for toolbar state ───────────────────────────────────
const LS = {
  get: (k, def) => { try { return JSON.parse(localStorage.getItem(k) ?? JSON.stringify(def)); } catch (_) { return def; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} },
};

export default function Chat({
  models = [],
  selectedModel = "",
  onModelChange,
  onModelsRefresh,
  searchQuery = "",
  onSearchMatchCount,
  searchMatchIndex = 0,
  onMessagesChange,
  currentSessionId,
  onSessionIdChange,
  onNewChat,
}) {
  const [messages, setMessages]         = useState([]);
  const [input, setInput]               = useState("");
  const [sending, setSending]           = useState(false);
  const [pendingNotifications, setPending] = useState([]);

  // Hover action state
  const [hoveredMsgIdx, setHoveredMsgIdx] = useState(null);

  // Refresh confirmation
  const [showRefreshConfirm, setShowRefreshConfirm] = useState(false);

  // Artifacts
  const [artifacts, setArtifacts]       = useState([]);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [showModelSidebar, setShowModelSidebar] = useState(false);

  // Toolbar lifted state (persisted to localStorage)
  const [agentMode, setAgentMode]         = useState(() => LS.get("roamin_agent_mode", "auto"));
  const [permission, setPermission]       = useState(() => LS.get("roamin_permission", "default"));
  const [projectPath, setProjectPath]     = useState(() => LS.get("roamin_project_path", ""));
  const [contextAttachment, setContextAttachment] = useState("");

  // Per-message agentic loop toggle (Option 1). null = defer to global setting.
  const [agenticEnabled, setAgenticEnabled] = useState(() => LS.get("roamin_agentic_enabled", null));

  // AbortController for stop-generation
  const abortControllerRef = useRef(null);
  const chatEndRef          = useRef(null);
  const textareaRef         = useRef(null);

  // Notify parent whenever messages change
  useEffect(() => { onMessagesChange?.(messages); }, [messages]); // eslint-disable-line

  // Persist toolbar choices
  useEffect(() => { LS.set("roamin_agent_mode", agentMode); }, [agentMode]);
  useEffect(() => { LS.set("roamin_permission", permission); }, [permission]);
  useEffect(() => { LS.set("roamin_project_path", projectPath); }, [projectPath]);
  useEffect(() => { LS.set("roamin_agentic_enabled", agenticEnabled); }, [agenticEnabled]);

  // Load history on mount or session change
  useEffect(() => {
    getChatHistory(currentSessionId)
      .then((data) => {
        if (data.exchanges?.length > 0) {
          const parsed = data.exchanges.map((ex) => {
            const content = ex.content || "";
            const isUser = /^(User|Asherre):/i.test(content);
            return {
              role: isUser ? "user" : "assistant",
              text: content.replace(/^(User|Asherre|Roamin):\s*/i, ""),
              timestamp: ex.timestamp,
            };
          });
          setMessages(parsed);
          if (data.session_id) onSessionIdChange?.(data.session_id);
        } else {
          setMessages([]);
        }
      })
      .catch(() => {});

    getPendingNotifications()
      .then((data) => {
        if (data.messages?.length > 0) setPending(data.messages);
      })
      .catch(() => {});
  }, [currentSessionId]); // eslint-disable-line

  // Auto-scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Search: count matches and notify parent
  useEffect(() => {
    if (!searchQuery) { onSearchMatchCount?.(0); return; }
    const re = new RegExp(searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const count = messages.reduce((sum, m) => {
      const matches = (m.text || "").match(re);
      return sum + (matches ? matches.length : 0);
    }, 0);
    onSearchMatchCount?.(count);
  }, [searchQuery, messages]); // eslint-disable-line

  // Auto-resize textarea
  const handleTextareaChange = (e) => {
    setInput(e.target.value);
    // JS fallback for browsers that don't support field-sizing: content
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const extra = {};
    if (projectPath) extra.project_path = projectPath;
    if (contextAttachment) extra.context_attachment = contextAttachment;
    if (agentMode !== "auto") extra.task = agentMode;
    if (permission !== "default") extra.permission_level = permission;
    if (agenticEnabled !== null) extra.agentic = agenticEnabled;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setContextAttachment("");
    setSending(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Unique sentinel index so we can update the in-progress message in place
    const assistantIdx = { current: -1 };

    const _addAssistant = (initial) => {
      setMessages((prev) => {
        assistantIdx.current = prev.length;
        return [...prev, { role: "assistant", ...initial }];
      });
    };

    const _updateAssistant = (patch) => {
      setMessages((prev) => {
        if (assistantIdx.current < 0 || assistantIdx.current >= prev.length) return prev;
        const updated = [...prev];
        updated[assistantIdx.current] = { ...updated[assistantIdx.current], ...patch };
        return updated;
      });
    };

    // ── Try SSE streaming first ──
    let usedStream = false;
    try {
      // Build base URL from current connection (pull from window global or fallback)
      const base = window.__CONTROL_API_URL__
        || (await (async () => {
          for (let p = 8765; p <= 8775; p++) {
            try {
              const r = await fetch(`http://127.0.0.1:${p}/status`, { cache: "no-store", signal: controller.signal });
              if (r.ok) return `http://127.0.0.1:${p}`;
            } catch (_) {}
          }
          return null;
        })());

      if (!base) throw new Error("backend not found");

      const resp = await fetch(`${base}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, include_screen: false, ...extra }),
        signal: controller.signal,
      });

      if (!resp.ok) throw new Error(`stream HTTP ${resp.status}`);
      usedStream = true;

      let thinkText = "";
      let replyText = "";
      let thinkStreaming = false; // eslint-disable-line no-unused-vars

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      // Add placeholder message immediately — includes agentic tracking fields
      _addAssistant({
        text: "", reasoning: null, thinkSeconds: null, _streaming: true,
        _planning: false, _planSteps: null, _planSeconds: null,
        _toolSteps: [], _reflecting: false, _reflectCycles: [],
      });

      // Mutable ref for tool steps (we mutate in place to avoid stale closures)
      const toolStepsRef = { current: [] };
      const reflectCyclesRef = { current: [] };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // Split on SSE event boundary (\n\n) — each entry is one complete event.
        const events = buf.split("\n\n");
        buf = events.pop(); // last fragment is incomplete — keep buffered

        for (const rawEvent of events) {
          let evtType = ""; // scoped per-event, not per-chunk
          let dataStr  = "";
          for (const line of rawEvent.split("\n")) {
            if (line.startsWith("event: ")) evtType = line.slice(7).trim();
            else if (line.startsWith("data: "))  dataStr  = line.slice(6);
          }
          if (!evtType || !dataStr) continue;

          let payload;
          try { payload = JSON.parse(dataStr); } catch (_) { continue; }

          if (evtType === "thinking_start") {
            thinkStreaming = true;
            _updateAssistant({ reasoning: "", thinkSeconds: null, _thinkStreaming: true });
          } else if (evtType === "thinking_delta") {
            thinkText += payload.text || "";
            _updateAssistant({ reasoning: thinkText, _thinkStreaming: true });
          } else if (evtType === "thinking_stop") {
            thinkStreaming = false;
            _updateAssistant({ thinkSeconds: payload.seconds || null, _thinkStreaming: false });
          } else if (evtType === "content_delta") {
            replyText += payload.text || "";
            _updateAssistant({ text: replyText });
          } else if (evtType === "done") {
            const finalArtifacts = extractArtifacts(replyText);
            if (finalArtifacts.length > 0) setArtifacts((p) => [...p, ...finalArtifacts]);
            _updateAssistant({
              text: replyText || "Done.", _streaming: false, _thinkStreaming: false,
              _planning: false, _reflecting: false,
              _toolSteps: toolStepsRef.current.map((s) => ({ ...s, status: s.status === "running" ? "ok" : s.status })),
              artifacts: finalArtifacts,
            });
          } else if (evtType === "error") {
            _updateAssistant({ text: `Error: ${payload.message || "unknown"}`, _streaming: false, _thinkStreaming: false });

          // ── Option 1 agentic events ──
          } else if (evtType === "planning_start") {
            _updateAssistant({ _planning: true, _planSteps: null, _planSeconds: null });
          } else if (evtType === "planning_stop") {
            _updateAssistant({ _planning: false, _planSteps: payload.steps ?? null, _planSeconds: payload.seconds ?? null });
          } else if (evtType === "tool_start") {
            const step = { tool: payload.tool, step: payload.step, action: payload.action || payload.tool, status: "running", seconds: null, error: null };
            toolStepsRef.current = [...toolStepsRef.current, step];
            _updateAssistant({ _toolSteps: [...toolStepsRef.current] });
          } else if (evtType === "tool_stop") {
            toolStepsRef.current = toolStepsRef.current.map((s) =>
              s.step === payload.step && s.tool === payload.tool
                ? { ...s, status: "ok", seconds: payload.seconds ?? null }
                : s
            );
            _updateAssistant({ _toolSteps: [...toolStepsRef.current] });
          } else if (evtType === "tool_error") {
            toolStepsRef.current = toolStepsRef.current.map((s) =>
              s.step === payload.step && s.tool === payload.tool
                ? { ...s, status: "error", error: payload.error || "failed" }
                : s
            );
            _updateAssistant({ _toolSteps: [...toolStepsRef.current] });
          } else if (evtType === "reflect_start") {
            _updateAssistant({ _reflecting: true });
          } else if (evtType === "reflect_stop") {
            const rc = { cycle: payload.cycle, verdict: payload.verdict, tool: payload.tool || null, seconds: payload.seconds ?? null };
            reflectCyclesRef.current = [...reflectCyclesRef.current, rc];
            _updateAssistant({ _reflecting: false, _reflectCycles: [...reflectCyclesRef.current] });
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        if (assistantIdx.current >= 0) {
          _updateAssistant({ text: "(stopped)", _streaming: false, _thinkStreaming: false });
        } else {
          setMessages((prev) => [...prev, { role: "assistant", text: "(stopped)" }]);
        }
        setSending(false);
        abortControllerRef.current = null;
        return;
      }

      // ── Fallback to non-streaming /chat ──
      if (!usedStream) {
        try {
          const result = await sendMessage(text, false, controller.signal, extra);
          const reply = result.response || "Done.";
          const newArtifacts = extractArtifacts(reply);
          if (newArtifacts.length > 0) setArtifacts((p) => [...p, ...newArtifacts]);
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              text: reply,
              reasoning: result.reasoning || null,
              thinkSeconds: result.think_seconds || null,
              artifacts: newArtifacts,
            },
          ]);
        } catch (fallbackErr) {
          console.error("[Chat] fallback /chat failed:", fallbackErr);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", text: `Error: ${fallbackErr.message || "Something went wrong."}` },
          ]);
        }
      } else {
        console.error("[Chat] stream error:", err);
        if (assistantIdx.current >= 0) {
          _updateAssistant({ text: `Error: ${err.message}`, _streaming: false });
        }
      }
    } finally {
      setSending(false);
      abortControllerRef.current = null;
    }
  }, [input, sending, agentMode, permission, projectPath, contextAttachment]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const handleRefresh = async () => {
    setShowRefreshConfirm(false);
    try { await resetChat(); } catch (_) {}
    setMessages([]);
    setArtifacts([]);
    onSessionIdChange?.(null);
  };

  const handleRetry = useCallback(async () => {
    if (sending) return;
    // Find the last user message
    const lastUserIdx = [...messages].reverse().findIndex((m) => m.role === "user");
    if (lastUserIdx === -1) return;
    const realIdx = messages.length - 1 - lastUserIdx;
    const userMsg = messages[realIdx];

    // Remove messages from that user message onward
    setMessages((prev) => prev.slice(0, realIdx));
    setInput(userMsg.text);
    // Re-trigger send on next tick
    setTimeout(() => {
      setInput(userMsg.text);
    }, 0);
  }, [messages, sending]);

  const handleEdit = useCallback((msgIdx) => {
    const msg = messages[msgIdx];
    if (!msg || msg.role !== "user") return;
    // Remove this message and everything after
    setMessages((prev) => prev.slice(0, msgIdx));
    setInput(msg.text);
    textareaRef.current?.focus();
  }, [messages]);

  const handleCopy = useCallback((text) => {
    navigator.clipboard.writeText(text).catch(() => {});
  }, []);

  // Count global search match offset for this message
  let globalMatchOffset = 0;

  return (
    <>
      <div className="chat-area">
        {/* Pending notifications banner */}
        {pendingNotifications.length > 0 && (
          <div className="pending-banner">
            <strong>Roamin wanted to say:</strong>
            {pendingNotifications.map((n, i) => (
              <div key={i} style={{ marginTop: 4 }}>{n.message || n}</div>
            ))}
            <button
              style={{ marginTop: 6, fontSize: 11, padding: "2px 8px", cursor: "pointer" }}
              onClick={() => setPending([])}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg, i) => {
          const isLast = i === messages.length - 1;
          const isLastUser = msg.role === "user" && messages.slice(i + 1).every((m) => m.role !== "user");
          const isLastAssistant = msg.role === "assistant" && isLast;

          // Compute how many search matches precede this message for active-highlight offset
          let myMatchOffset = globalMatchOffset;
          if (searchQuery) {
            const re = new RegExp(searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
            const prevMatches = messages.slice(0, i).reduce((sum, m) => {
              const hits = (m.text || "").match(re);
              return sum + (hits ? hits.length : 0);
            }, 0);
            myMatchOffset = prevMatches;
          }

          // Which match within this message is the active one?
          const activeLocalIdx = searchMatchIndex - myMatchOffset;

          return (
            <div
              key={i}
              className={`message-wrapper ${msg.role}`}
              onMouseEnter={() => setHoveredMsgIdx(i)}
              onMouseLeave={() => setHoveredMsgIdx(null)}
            >
              {/* Option 1 agentic status — plan/tool/reflect events */}
              {msg.role === "assistant" && (msg._planning || msg._toolSteps?.length > 0 || msg._reflecting || msg._reflectCycles?.length > 0) && (
                <ToolStatus
                  planning={!!msg._planning}
                  planSeconds={msg._planSeconds ?? null}
                  planSteps={msg._planSteps ?? null}
                  toolSteps={msg._toolSteps || []}
                  reflecting={!!msg._reflecting}
                  reflectCycles={msg._reflectCycles || []}
                />
              )}

              {/* Reasoning block — only render once thinking_start has fired (reasoning !== null) */}
              {msg.role === "assistant" && msg.reasoning !== null && (
                <ThinkingBlock
                  reasoning={msg.reasoning}
                  thinkSeconds={msg.thinkSeconds}
                  streaming={!!msg._thinkStreaming}
                />
              )}

              <div className={`message ${msg.role}`}>
                <div className="role">{msg.role === "user" ? "You" : "Roamin"}</div>
                <div className="text">
                  {msg._streaming && !msg.text && msg.reasoning === null
                    ? <div className="thinking-skeleton" />
                    : searchQuery
                      ? highlightText(msg.text, searchQuery, activeLocalIdx >= 0)
                      : msg.text
                  }
                </div>
                {/* Artifact chip */}
                {msg.artifacts?.length > 0 && (
                  <div
                    className="artifact-chip"
                    onClick={() => setShowArtifacts(true)}
                  >
                    ⎘ {msg.artifacts.length} artifact{msg.artifacts.length > 1 ? "s" : ""} →
                  </div>
                )}
              </div>

              {/* Hover action buttons */}
              {hoveredMsgIdx === i && (
                <div className="message-actions">
                  {/* Copy (all messages) */}
                  <button
                    className="message-action-btn"
                    title="Copy message"
                    onClick={() => handleCopy(msg.text)}
                  >
                    ⎘
                  </button>

                  {/* Edit (user messages only) */}
                  {msg.role === "user" && isLastUser && (
                    <button
                      className="message-action-btn"
                      title="Edit message"
                      onClick={() => handleEdit(i)}
                    >
                      ✏
                    </button>
                  )}

                  {/* Retry (last assistant message only) */}
                  {msg.role === "assistant" && isLastAssistant && !sending && (
                    <button
                      className="message-action-btn"
                      title="Regenerate response"
                      onClick={handleRetry}
                    >
                      ↺
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}

        <div ref={chatEndRef} />
      </div>

      {/* ── Input area ── */}
      <div style={{ background: "var(--bg-secondary)", borderTop: "1px solid var(--border)" }}>
        {/* Token usage bar */}
        <TokenBar messages={messages} />

        {/* Textarea + send/stop */}
        <div className="input-send-area">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message…"
            disabled={sending}
            rows={1}
            autoFocus
          />
          {sending ? (
            <button className="btn-stop" onClick={handleStop} title="Stop generation">
              ■ Stop
            </button>
          ) : (
            <button
              style={{
                padding: "8px 16px",
                background: "var(--accent)",
                color: "white",
                border: "none",
                borderRadius: 8,
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 500,
                opacity: !input.trim() ? 0.5 : 1,
              }}
              onClick={handleSend}
              disabled={!input.trim()}
              title="Send (Enter)"
            >
              ➤
            </button>
          )}

          {/* Refresh with confirmation */}
          <div style={{ position: "relative" }}>
            <button
              className="chat-refresh-btn"
              title="Refresh chat"
              onClick={() => setShowRefreshConfirm((v) => !v)}
            >
              ↺
            </button>
            {showRefreshConfirm && (
              <div className="confirm-popover">
                <span>Refresh this chat?</span>
                <div className="confirm-popover-actions">
                  <button className="confirm-cancel" onClick={() => setShowRefreshConfirm(false)}>
                    Cancel
                  </button>
                  <button className="confirm-ok" onClick={handleRefresh}>
                    Refresh
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Toolbar row */}
        <InputToolbar
          models={models}
          selectedModel={selectedModel}
          onModelChange={onModelChange}
          onModelsRefresh={onModelsRefresh}
          agentMode={agentMode}
          onAgentModeChange={setAgentMode}
          permission={permission}
          onPermissionChange={setPermission}
          projectPath={projectPath}
          onProjectPathChange={setProjectPath}
          contextAttachment={contextAttachment}
          onContextAttachmentChange={setContextAttachment}
          onOpenModelSidebar={() => setShowModelSidebar(true)}
          agenticEnabled={agenticEnabled}
          onAgenticChange={setAgenticEnabled}
        />
      </div>

      {/* ── Right-side overlay panels (one at a time) ── */}
      {showArtifacts && (
        <ArtifactsPanel
          artifacts={artifacts}
          onClose={() => setShowArtifacts(false)}
        />
      )}

      {showModelSidebar && !showArtifacts && (
        <ModelSidebar
          onClose={() => setShowModelSidebar(false)}
          selectedModel={selectedModel}
          models={models}
        />
      )}
    </>
  );
}
