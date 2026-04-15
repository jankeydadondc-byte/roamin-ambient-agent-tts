import React, { useState, useEffect } from "react";
import { getSessions, resetChat, deleteSession } from "../apiClient";

/**
 * Left-overlay panel showing session history with delete support.
 * @param {string}   currentSessionId
 * @param {Function} onSessionSelect(sessionId) - load a past session
 * @param {Function} onNewChat                  - start a fresh session
 * @param {Function} onClose
 */
export default function SessionSidebar({ currentSessionId, onSessionSelect, onNewChat, onClose }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null); // session_id being deleted
  // Custom titles stored in localStorage: { [session_id]: "My title" }
  const [titles, setTitles] = useState(() => {
    try { return JSON.parse(localStorage.getItem("roamin_session_titles") || "{}"); }
    catch (_) { return {}; }
  });
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");

  const loadSessions = () => {
    setLoading(true);
    getSessions()
      .then((data) => setSessions(data.sessions || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadSessions(); }, []);

  const getTitle = (s) => {
    if (titles[s.session_id]) return titles[s.session_id];
    return (s.first_message || "").replace(/^(User|Asherre|Roamin):\s*/i, "").slice(0, 50) || "Untitled";
  };

  const saveTitle = (sessionId, value) => {
    const updated = { ...titles, [sessionId]: value };
    setTitles(updated);
    localStorage.setItem("roamin_session_titles", JSON.stringify(updated));
    setEditingId(null);
  };

  const handleDelete = async (e, sessionId) => {
    e.stopPropagation();
    setDeleting(sessionId);
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      // Clean up localStorage title
      const updated = { ...titles };
      delete updated[sessionId];
      setTitles(updated);
      localStorage.setItem("roamin_session_titles", JSON.stringify(updated));
      // If deleted the active session, start fresh
      if (sessionId === currentSessionId) {
        onNewChat();
      }
    } catch (err) {
      console.error("[SessionSidebar] Delete failed:", err);
    } finally {
      setDeleting(null);
    }
  };

  const handleDeleteAll = async () => {
    setDeleting("__all__");
    try {
      // Delete all sessions one by one
      for (const s of sessions) {
        await deleteSession(s.session_id);
      }
      setSessions([]);
      setTitles({});
      localStorage.setItem("roamin_session_titles", "{}");
      onNewChat();
    } catch (err) {
      console.error("[SessionSidebar] Delete all failed:", err);
      loadSessions(); // reload whatever survived
    } finally {
      setDeleting(null);
    }
  };

  const relativeTime = (ts) => {
    if (!ts) return "";
    try {
      const diff = Date.now() - new Date(ts).getTime();
      const mins = Math.round(diff / 60000);
      if (mins < 2) return "just now";
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.round(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      return `${Math.round(hrs / 24)}d ago`;
    } catch (_) { return ""; }
  };

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay left">
        <div className="sidebar-header">
          <span>Sessions</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>
        <div className="sidebar-body">
          <div style={{ display: "flex", gap: 6, padding: "0 10px 6px" }}>
            <button className="session-new-btn" style={{ flex: 1 }} onClick={() => { onNewChat(); onClose(); }}>
              ＋ New Chat
            </button>
            {sessions.length > 0 && (
              <button
                className="session-new-btn"
                style={{ flex: 0, padding: "6px 10px", background: "rgba(224,108,117,0.15)", color: "#e06c75", fontSize: 11 }}
                title="Delete all sessions"
                onClick={handleDeleteAll}
                disabled={deleting === "__all__"}
              >
                {deleting === "__all__" ? "…" : "🗑 All"}
              </button>
            )}
          </div>

          {loading && (
            <div style={{ padding: "12px 14px", fontSize: 12, color: "var(--text-secondary)" }}>
              Loading…
            </div>
          )}

          {!loading && sessions.length === 0 && (
            <div style={{ padding: "12px 14px", fontSize: 12, color: "var(--text-secondary)" }}>
              No past sessions found.
            </div>
          )}

          {sessions.map((s) => (
            <div
              key={s.session_id}
              className={`session-row ${s.session_id === currentSessionId ? "active" : ""}`}
              onClick={() => { onSessionSelect(s.session_id); onClose(); }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 4 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {editingId === s.session_id ? (
                    <input
                      autoFocus
                      className="model-search"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => saveTitle(s.session_id, editValue)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveTitle(s.session_id, editValue);
                        if (e.key === "Escape") setEditingId(null);
                        e.stopPropagation();
                      }}
                      onClick={(e) => e.stopPropagation()}
                      style={{ margin: "0", width: "100%" }}
                    />
                  ) : (
                    <div
                      className="session-row-title"
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setEditingId(s.session_id);
                        setEditValue(getTitle(s));
                      }}
                      title="Double-click to rename"
                    >
                      {getTitle(s)}
                    </div>
                  )}
                  <div className="session-row-meta">
                    {relativeTime(s.last_at)} · {s.message_count} msgs
                  </div>
                </div>
                <button
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    fontSize: 12,
                    padding: "2px 4px",
                    opacity: deleting === s.session_id ? 0.4 : 0.6,
                    flexShrink: 0,
                  }}
                  title="Delete session"
                  onClick={(e) => handleDelete(e, s.session_id)}
                  disabled={deleting === s.session_id}
                >
                  {deleting === s.session_id ? "…" : "✕"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
