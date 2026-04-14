import React, { useState } from "react";

// Tauri v2 invoke — dialog plugin uses the plugin: namespace
const _tauriInvoke = window.__TAURI__?.core?.invoke ?? window.__TAURI__?.tauri?.invoke ?? null;

/**
 * Popover for setting the session's working-directory / project path.
 * Supports manual typing or a native folder-picker browse button (Tauri only).
 *
 * @param {string}   value    - current path
 * @param {Function} onChange - called with new path string
 * @param {Function} onClose
 */
export default function ProjectPicker({ value, onChange, onClose }) {
  const [draft, setDraft] = useState(value || "");
  const [browsing, setBrowsing] = useState(false);

  const handleSave = () => {
    onChange(draft.trim());
    onClose();
  };

  const handleBrowse = async () => {
    if (!_tauriInvoke) return; // not in Tauri — fall back to manual input
    setBrowsing(true);
    try {
      // Tauri v2 dialog plugin: plugin:dialog|open with directory:true
      const selected = await _tauriInvoke("plugin:dialog|open", {
        directory: true,
        multiple: false,
        title: "Select Project Folder",
      });
      if (selected && typeof selected === "string") {
        setDraft(selected);
      }
    } catch (e) {
      console.warn("[ProjectPicker] Browse failed:", e);
    } finally {
      setBrowsing(false);
    }
  };

  const isTauri = Boolean(_tauriInvoke);

  return (
    <div className="popover" style={{ minWidth: 260 }}>
      <div className="popover-title">Session Target</div>
      <div style={{ padding: "6px 12px 4px", fontSize: 11, color: "var(--text-secondary)" }}>
        Working directory prepended to chat context
      </div>
      <div style={{ display: "flex", gap: 6, padding: "0 12px 6px" }}>
        <input
          className="popover-path-input"
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") onClose(); }}
          placeholder="e.g. C:\AI\my-project"
          autoFocus={!isTauri}
          style={{ flex: 1, margin: 0 }}
        />
        {isTauri && (
          <button
            className="toolbar-btn"
            title="Browse for folder"
            onClick={handleBrowse}
            disabled={browsing}
            style={{ flexShrink: 0, fontSize: 14 }}
          >
            {browsing ? "…" : "📂"}
          </button>
        )}
      </div>
      <button className="popover-save-btn" onClick={handleSave}>
        Set Target
      </button>
      {value && (
        <div style={{ padding: "0 12px 6px", fontSize: 10, color: "var(--text-secondary)" }}>
          Current: {value}
        </div>
      )}
    </div>
  );
}
