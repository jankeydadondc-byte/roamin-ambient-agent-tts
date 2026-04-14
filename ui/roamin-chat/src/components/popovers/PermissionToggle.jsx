import React from "react";

const LEVELS = [
  {
    id: "default",
    label: "Default",
    desc: "Confirm each destructive action",
    color: "#2ecc71",
  },
  {
    id: "bypass",
    label: "Bypass Approvals",
    desc: "Skip confirmation for low-risk actions",
    color: "#f5a623",
  },
  {
    id: "autopilot",
    label: "Autopilot",
    desc: "No confirmations — all actions execute immediately",
    color: "#e74c3c",
  },
];

/**
 * Three-way permission level selector.
 * @param {string}   value    - current level id
 * @param {Function} onChange - called with new level id
 * @param {Function} onClose
 */
export default function PermissionToggle({ value, onChange, onClose }) {
  return (
    <div className="popover" style={{ minWidth: 220 }}>
      <div className="popover-title">Permissions</div>
      <div className="permission-options">
        {LEVELS.map((l) => (
          <React.Fragment key={l.id}>
            <div
              className={`permission-option ${value === l.id ? "selected" : ""}`}
              onClick={() => { onChange(l.id); onClose(); }}
            >
              <span
                className="permission-dot"
                style={{ background: value === l.id ? l.color : "var(--border)" }}
              />
              {l.label}
              {value === l.id && <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--accent)" }}>✓</span>}
            </div>
            <div className="permission-desc">{l.desc}</div>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
