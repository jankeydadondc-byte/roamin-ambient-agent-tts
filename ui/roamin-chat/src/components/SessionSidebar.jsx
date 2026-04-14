import React, { useState, useEffect } from "react";
import { getSessions, resetChat } from "../apiClient";

/**
 * Left-overlay panel showing session history.
 * @param {string}   currentSessionId
 * @param {Function} onSessionSelect(sessionId) - load a past session
 * @param {Function} onNewChat                  - start a fresh session
 * @param {Function} onClose
 */
export default function SessionSidebar({ currentSessionId, onSessionSelect, onNewChat, onClose }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  // Custom titles stored in localStorage: { [session_id]: "My title" }
  const [titles, setTitles] = useState(() => {
    try { return JSON.parse(localStorage.getItem("roamin_session_titles") || "{}"); }
    catch (_) { return {}; }
  });
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");

  useEffect(() => {
    getSessions()
      .then((data) => setSessions(data.sessions || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  const getTitle = (s) => {
    if (titles[s.session_id]) return titles[s.session_id];
    // Auto-title: strip "User:" prefix and take first 50 chars
    return (s.first_message || "").replace(/^(User|Asherre|Roamin):\s*/i, "").slice(0, 50) || "Untitled";
  };

  const saveTitle = (sessionId, value) => {
    const updated = { ...titles, [sessionId]: value };
    setTitles(updated);
    localStorage.setItem("roamin_session_titles", JSON.stringify(updated));
    setEditingId(null);
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
          <button className="session-new-btn" onClick={() => { onNewChat(); onClose(); }}>
            ＋ New Chat
          </button>

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
          ))}
        </div>
      </div>
    </>
  );
}
