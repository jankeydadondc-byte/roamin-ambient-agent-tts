import React, { useState } from "react";

/**
 * Popover for setting the session's working-directory / project path.
 * Value is persisted to localStorage and prepended to the chat context.
 * @param {string}   value    - current path
 * @param {Function} onChange - called with new path string
 * @param {Function} onClose
 */
export default function ProjectPicker({ value, onChange, onClose }) {
  const [draft, setDraft] = useState(value || "");

  const handleSave = () => {
    onChange(draft.trim());
    onClose();
  };

  return (
    <div className="popover" style={{ minWidth: 240 }}>
      <div className="popover-title">Session Target</div>
      <div style={{ padding: "6px 12px 4px", fontSize: 11, color: "var(--text-secondary)" }}>
        Working directory prepended to chat context
      </div>
      <input
        className="popover-path-input"
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") onClose(); }}
        placeholder="e.g. C:\AI\my-project"
        autoFocus
      />
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
