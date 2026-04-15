import React, { useState } from "react";

/**
 * Popover for attaching a file/folder path as context to the next message.
 * @param {string}   value    - current attachment path
 * @param {Function} onChange - called with new path string (or "" to clear)
 * @param {Function} onClose
 */
export default function ContextPicker({ value, onChange, onClose }) {
  const [draft, setDraft] = useState(value || "");

  const handleAttach = () => {
    onChange(draft.trim());
    onClose();
  };

  const handleClear = () => {
    onChange("");
    onClose();
  };

  return (
    <div className="popover" style={{ minWidth: 240 }} onMouseDown={(e) => e.stopPropagation()}>
      <div className="popover-title">Add Context</div>
      <div style={{ padding: "6px 12px 4px", fontSize: 11, color: "var(--text-secondary)" }}>
        File or folder path to include with your next message
      </div>
      <input
        className="popover-path-input"
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") handleAttach(); if (e.key === "Escape") onClose(); }}
        placeholder="e.g. C:\AI\project\main.py"
        autoFocus
      />
      <button className="popover-save-btn" onClick={handleAttach}>
        Attach
      </button>
      {value && (
        <div style={{ display: "flex", alignItems: "center", padding: "0 12px 8px", gap: 6 }}>
          <span style={{ fontSize: 10, color: "var(--accent)", flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
            📎 {value}
          </span>
          <button
            onClick={handleClear}
            style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 12 }}
            title="Remove attachment"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
