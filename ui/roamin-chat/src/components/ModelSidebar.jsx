import React, { useState, useEffect } from "react";
import { getCurrentModel, getSystemPrompt } from "../apiClient";

/**
 * Right-overlay panel showing active model info and system prompt.
 * @param {Function} onClose
 * @param {string}   selectedModel - the currently selected model id
 * @param {Array}    models        - full models list for display
 */
export default function ModelSidebar({ onClose, selectedModel, models = [] }) {
  const [routingData, setRoutingData] = useState(null);
  const [promptData, setPromptData] = useState(null);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [sidecarExpanded, setSidecarExpanded] = useState(false);

  useEffect(() => {
    getCurrentModel().then(setRoutingData).catch(() => setRoutingData(null));
    getSystemPrompt().then(setPromptData).catch(() => setPromptData(null));
  }, []);

  // Find the model entry for the currently selected model
  const activeModelEntry = models.find((m) => (m.id || m) === selectedModel) || null;
  const modelName = activeModelEntry?.name || selectedModel || "Auto (config default)";

  // Routing overrides
  const overrides = routingData?.overrides || {};
  const hasOverrides = Object.keys(overrides).length > 0;

  const prompts = promptData?.prompts || {};

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay right">
        <div className="sidebar-header">
          <span>Model Info</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>
        <div className="sidebar-body">
          {/* ── Active Model ── */}
          <div style={{ padding: "10px 12px 6px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-all" }}>
              {modelName}
            </div>
            {activeModelEntry?.provider && (
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                Provider: {activeModelEntry.provider}
              </div>
            )}
            {activeModelEntry?.status && (
              <div style={{ fontSize: 11, color: activeModelEntry.status === "loaded" ? "#4caf50" : "var(--text-secondary)", marginTop: 2 }}>
                Status: {activeModelEntry.status}
              </div>
            )}
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* ── Routing Overrides ── */}
          <div style={{ padding: "6px 12px" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
              Routing
            </div>
            {hasOverrides ? (
              Object.entries(overrides).map(([task, modelId]) => (
                <div key={task} style={{ fontSize: 11, color: "var(--text-secondary)", padding: "2px 0" }}>
                  <span style={{ color: "var(--accent)" }}>{task}</span>: {modelId}
                </div>
              ))
            ) : (
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                Using config defaults (no overrides active)
              </div>
            )}
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* ── Model Parameters Note ── */}
          <div style={{ padding: "6px 12px" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
              Parameters
            </div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Temperature, context length, top-K, top-P, and repeat penalty
              are configured directly in LM Studio's model settings panel.
              Changes take effect immediately for the loaded model.
            </div>
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* ── System Prompt (Primary) ── */}
          <div
            style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", userSelect: "none" }}
            onClick={() => setPromptExpanded(!promptExpanded)}
          >
            {promptExpanded ? "▾" : "▸"} System Prompt (personality)
          </div>
          {promptExpanded && (
            <div className="model-system-prompt-block">
              {prompts.primary || "Not found — create 'roamin ambient agent system prompt.txt' in project root."}
            </div>
          )}

          {/* ── System Prompt (Sidecar) ── */}
          <div
            style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", userSelect: "none" }}
            onClick={() => setSidecarExpanded(!sidecarExpanded)}
          >
            {sidecarExpanded ? "▾" : "▸"} System Prompt (sidecar persona)
          </div>
          {sidecarExpanded && (
            <div className="model-system-prompt-block">
              {prompts.sidecar || "Not found — create 'agent/core/system_prompt.txt'."}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
