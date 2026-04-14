import React from "react";

const AGENTS = [
  { id: "auto",      label: "Auto",      desc: "Let Roamin decide the best mode" },
  { id: "chat",      label: "Chat",      desc: "Conversational — no tool use" },
  { id: "code",      label: "Code",      desc: "Routes to the code model" },
  { id: "reasoning", label: "Reasoning", desc: "Routes to the reasoning model" },
];

/**
 * Popover for selecting agent/task mode.
 * @param {string}   value    - current agent mode id
 * @param {Function} onChange - called with new agent id
 * @param {Function} onClose
 */
export default function AgentPicker({ value, onChange, onClose }) {
  return (
    <div className="popover" style={{ minWidth: 210 }}>
      <div className="popover-title">Agent Mode</div>
      {AGENTS.map((a) => (
        <div
          key={a.id}
          className={`popover-option ${value === a.id ? "selected" : ""}`}
          onClick={() => { onChange(a.id); onClose(); }}
        >
          <span className="popover-option-check">{value === a.id ? "✓" : ""}</span>
          <div>
            <div>{a.label}</div>
            <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>{a.desc}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
