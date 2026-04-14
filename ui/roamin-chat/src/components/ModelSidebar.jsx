import React, { useState, useEffect } from "react";
import { getCurrentModel } from "../apiClient";

/**
 * Right-overlay panel showing active model parameters (read-only in v1).
 * @param {Function} onClose
 */
export default function ModelSidebar({ onClose }) {
  const [modelData, setModelData] = useState(null);
  const [systemExpanded, setSystemExpanded] = useState(false);

  useEffect(() => {
    getCurrentModel()
      .then(setModelData)
      .catch(() => setModelData(null));
  }, []);

  const routing = modelData?.routing || {};
  const activeModel = Object.values(routing)[0] || null;

  const PARAMS = [
    { key: "temperature",     label: "Temperature",     min: 0, max: 2,   step: 0.05 },
    { key: "top_p",           label: "Top P",           min: 0, max: 1,   step: 0.01 },
    { key: "top_k",           label: "Top K",           min: 1, max: 200, step: 1    },
    { key: "repeat_penalty",  label: "Repeat Penalty",  min: 0.8, max: 1.5, step: 0.01 },
  ];

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay right">
        <div className="sidebar-header">
          <span>Model Settings</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>
        <div className="sidebar-body">
          {!modelData ? (
            <div style={{ padding: "12px 14px", fontSize: 12, color: "var(--text-secondary)" }}>
              Loading model info…
            </div>
          ) : (
            <>
              <div style={{ padding: "10px 12px 4px" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                  {activeModel?.model_id || "Unknown model"}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                  Active routing target
                  <span className="model-readonly-badge">read-only</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4, opacity: 0.7 }}>
                  Parameters are configured in LM Studio. This panel is informational.
                </div>
              </div>

              <div style={{ height: 1, background: "var(--border)", margin: "8px 0" }} />

              {PARAMS.map(({ key, label, min, max, step }) => {
                const val = activeModel?.[key];
                return (
                  <div key={key} className="model-param-row">
                    <div className="model-param-label">
                      <span>{label}</span>
                      <span>{val !== undefined && val !== null ? val : "—"}</span>
                    </div>
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={step}
                      value={val !== undefined && val !== null ? val : (min + max) / 2}
                      disabled
                      style={{ opacity: 0.5 }}
                    />
                  </div>
                );
              })}

              {activeModel?.context_length != null && (
                <div className="model-param-row">
                  <div className="model-param-label">
                    <span>Context Length</span>
                    <span>{activeModel.context_length?.toLocaleString() ?? "—"}</span>
                  </div>
                  <input
                    type="number"
                    value={activeModel.context_length ?? ""}
                    disabled
                    style={{ opacity: 0.5 }}
                  />
                </div>
              )}

              <div style={{ height: 1, background: "var(--border)", margin: "8px 0" }} />

              <div
                style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-secondary)", cursor: "pointer" }}
                onClick={() => setSystemExpanded(!systemExpanded)}
              >
                {systemExpanded ? "▾" : "▸"} System Prompt
              </div>
              {systemExpanded && (
                <div className="model-system-prompt-block">
                  {activeModel?.system_prompt || modelData?.system_prompt || "No system prompt info available."}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
