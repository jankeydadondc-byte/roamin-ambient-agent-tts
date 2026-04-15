import React, { useState, useEffect, useRef, useCallback } from "react";
import Chat from "./components/Chat";
import SettingsPanel from "./components/SettingsPanel";
import SessionSidebar from "./components/SessionSidebar";
import SearchBar from "./components/SearchBar";
import {
  getModels,
  selectModel,
  resetChat,
  connectEvents,
  onConnectionChange,
} from "./apiClient";
import { exportChat } from "./utils/exportChat";

const CONN_STYLES = {
  connecting:   { color: "#f5a623", label: "Connecting…" },
  connected:    { color: "#4caf50", label: "Connected" },
  disconnected: { color: "#e53935", label: "Disconnected" },
};

export default function App() {
  const [models, setModels]               = useState([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  // Restore last-selected model from localStorage so it survives page refresh
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem("roamin_selected_model") || ""
  );
  const [connState, setConnState]         = useState("connecting");

  // Panel visibility
  const [showSettings, setShowSettings]   = useState(false);
  const [showHistory, setShowHistory]     = useState(false);

  // Search
  const [showSearch, setShowSearch]       = useState(false);
  const [searchQuery, setSearchQuery]     = useState("");
  const [searchMatchIndex, setSearchMatchIndex] = useState(0);
  const [searchMatchCount, setSearchMatchCount] = useState(0);

  // Active session for history sidebar
  const [currentSessionId, setCurrentSessionId] = useState(null);

  // Expose messages ref so App can drive export without prop-drilling
  const messagesRef = useRef([]);

  const prevConnState = useRef(null);

  const loadModels = useCallback(() => {
    setModelsLoading(true);
    getModels()
      .then((data) => {
        setModels(data.models || []);
        // Don't auto-select first model — "Auto" (empty) is the default
        // The user's last manual selection is restored from localStorage above
      })
      .catch(() => setModels([]))
      .finally(() => setModelsLoading(false));
  }, []);

  useEffect(() => {
    const unsub = onConnectionChange((state) => {
      setConnState(state);
      if (state === "connected" && prevConnState.current !== "connected") {
        loadModels();
      }
      prevConnState.current = state;
    });
    loadModels();
    const conn = connectEvents(() => {});

    // Restore always-on-top from localStorage on mount
    const _invoke = window.__TAURI__?.core?.invoke ?? window.__TAURI__?.tauri?.invoke;
    if (_invoke) {
      const saved = localStorage.getItem("alwaysOnTop") === "true";
      _invoke("set_always_on_top", { onTop: saved }).catch(() => {});
    }

    return () => { unsub(); conn.close(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard shortcut: Ctrl+F → open search
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        setShowSearch((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleModelChange = (modelId) => {
    setSelectedModel(modelId);
    localStorage.setItem("roamin_selected_model", modelId || "");
    selectModel(modelId).catch((err) =>
      console.error("[App] Model switch failed:", err)
    );
  };

  const handleModelsRefresh = (freshModels) => {
    setModels(freshModels);
  };

  const handleNewChat = async () => {
    try {
      await resetChat();
    } catch (_) {}
    setCurrentSessionId(null);
  };

  const handleExport = () => {
    exportChat(messagesRef.current);
  };

  const connStyle = CONN_STYLES[connState] || CONN_STYLES.disconnected;

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <h1>Roamin</h1>
        <div className="header-controls">
          {/* Connection dot */}
          <span
            title={connStyle.label}
            style={{
              display: "inline-block",
              width: 9,
              height: 9,
              borderRadius: "50%",
              background: connStyle.color,
              flexShrink: 0,
              boxShadow: connState === "connected" ? `0 0 4px ${connStyle.color}` : "none",
              transition: "background 0.3s, box-shadow 0.3s",
            }}
          />

          {/* New chat */}
          <button
            className="header-icon-btn"
            title="New chat"
            onClick={handleNewChat}
          >
            ＋
          </button>

          {/* History sidebar */}
          <button
            className={`header-icon-btn ${showHistory ? "active" : ""}`}
            title="Session history"
            onClick={() => setShowHistory((v) => !v)}
          >
            ☰
          </button>

          {/* In-chat search */}
          <button
            className={`header-icon-btn ${showSearch ? "active" : ""}`}
            title="Search in chat (Ctrl+F)"
            onClick={() => setShowSearch((v) => !v)}
          >
            🔍
          </button>

          {/* Export */}
          <button
            className="header-icon-btn"
            title="Export conversation"
            onClick={handleExport}
          >
            ↓
          </button>

          {/* Settings slide-over */}
          <button
            className={`header-icon-btn ${showSettings ? "active" : ""}`}
            title="Settings"
            onClick={() => setShowSettings((v) => !v)}
          >
            ⚙
          </button>
        </div>
      </header>

      {/* ── Search bar (slides down from header) ── */}
      {showSearch && (
        <SearchBar
          query={searchQuery}
          onChange={(q) => { setSearchQuery(q); setSearchMatchIndex(0); }}
          matchCount={searchMatchCount}
          matchIndex={searchMatchIndex}
          onPrev={() => setSearchMatchIndex((i) => Math.max(0, i - 1))}
          onNext={() => setSearchMatchIndex((i) => Math.min(searchMatchCount - 1, i + 1))}
          onClose={() => { setShowSearch(false); setSearchQuery(""); }}
        />
      )}

      {/* ── Main chat ── */}
      <Chat
        models={models}
        selectedModel={selectedModel}
        onModelChange={handleModelChange}
        onModelsRefresh={handleModelsRefresh}
        searchQuery={searchQuery}
        onSearchMatchCount={setSearchMatchCount}
        searchMatchIndex={searchMatchIndex}
        onMessagesChange={(msgs) => { messagesRef.current = msgs; }}
        currentSessionId={currentSessionId}
        onSessionIdChange={setCurrentSessionId}
        onNewChat={handleNewChat}
      />

      {/* ── Overlay panels ── */}
      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          selectedModel={selectedModel}
          onModelChange={handleModelChange}
          models={models}
          onModelsRefresh={handleModelsRefresh}
        />
      )}

      {showHistory && (
        <SessionSidebar
          currentSessionId={currentSessionId}
          onSessionSelect={(id) => {
            setCurrentSessionId(id);
          }}
          onNewChat={handleNewChat}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
}
