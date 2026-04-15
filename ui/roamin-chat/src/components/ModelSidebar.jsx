import React, { useState, useEffect } from "react";
import { getCurrentModel, getSystemPrompt, getModelParams, setModelParams } from "../apiClient";

/**
 * Right-overlay panel showing active model info, editable parameters, and system prompt.
 * @param {Function} onClose
 * @param {string}   selectedModel - the currently selected model id
 * @param {Array}    models        - full models list for display
 */
export default function ModelSidebar({ onClose, selectedModel, models = [] }) {
  const [routingData, setRoutingData] = useState(null);
  const [promptData, setPromptData] = useState(null);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [sidecarExpanded, setSidecarExpanded] = useState(false);

  // Model params state
  const [params, setParams] = useState({
    temperature: 0.7,
    top_p: 0.95,
    top_k: 40,
    repeat_penalty: 1.1,
    max_tokens: 2048,
    context_length: 8192,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getCurrentModel().then(setRoutingData).catch(() => setRoutingData(null));
    getSystemPrompt().then(setPromptData).catch(() => setPromptData(null));
    getModelParams().then((d) => {
      if (d && d.params) setParams((prev) => ({ ...prev, ...d.params }));
    }).catch(() => {});
  }, []);

  const activeModelEntry = models.find((m) => (m.id || m) === selectedModel) || null;
  const modelName = activeModelEntry?.name || selectedModel || "Auto (config default)";

  const overrides = routingData?.overrides || {};
  const hasOverrides = Object.keys(overrides).length > 0;
  const prompts = promptData?.prompts || {};

  const statusColors = {
    loaded: "#4caf50",
    available: "var(--accent)",
    missing: "#e06c75",
    unavailable: "var(--text-secondary)",
  };

  const handleParamChange = (key, value) => {
    setParams((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    await setModelParams(params);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setParams({
      temperature: 0.7,
      top_p: 0.95,
      top_k: 40,
      repeat_penalty: 1.1,
      max_tokens: 2048,
      context_length: 8192,
    });
    setSaved(false);
  };

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay right">
        <div className="sidebar-header">
          <span>Model Info</span>
          <button className="sidebar-close-btn" onClick={onClose}>&#10005;</button>
        </div>
        <div className="sidebar-body">
          {/* Active Model */}
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
              <div style={{
                fontSize: 11,
                color: statusColors[activeModelEntry.status] || "var(--text-secondary)",
                marginTop: 2,
              }}>
                Status: {activeModelEntry.status}
              </div>
            )}
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* Routing */}
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

          {/* Parameters — Editable */}
          <div style={{ padding: "6px 12px" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
              Parameters
            </div>

            {/* Temperature */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Temperature</span>
                <span>{params.temperature}</span>
              </div>
              <input
                type="range" min={0} max={2} step={0.05}
                value={params.temperature}
                onChange={(e) => handleParamChange("temperature", parseFloat(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* Top P */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Top P</span>
                <span>{params.top_p}</span>
              </div>
              <input
                type="range" min={0} max={1} step={0.01}
                value={params.top_p}
                onChange={(e) => handleParamChange("top_p", parseFloat(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* Top K */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Top K</span>
                <span>{params.top_k}</span>
              </div>
              <input
                type="range" min={1} max={200} step={1}
                value={params.top_k}
                onChange={(e) => handleParamChange("top_k", parseInt(e.target.value, 10))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* Repeat Penalty */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Repeat Penalty</span>
                <span>{params.repeat_penalty}</span>
              </div>
              <input
                type="range" min={0.8} max={1.5} step={0.01}
                value={params.repeat_penalty}
                onChange={(e) => handleParamChange("repeat_penalty", parseFloat(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* Max Tokens */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Max Tokens</span>
              </div>
              <input
                type="number" min={64} max={32768} step={64}
                value={params.max_tokens}
                onChange={(e) => handleParamChange("max_tokens", parseInt(e.target.value, 10) || 2048)}
                className="model-param-number-input"
              />
            </div>

            {/* Context Length */}
            <div className="model-param-row">
              <div className="model-param-label">
                <span>Context Length</span>
              </div>
              <input
                type="number" min={512} max={262144} step={512}
                value={params.context_length}
                onChange={(e) => handleParamChange("context_length", parseInt(e.target.value, 10) || 8192)}
                className="model-param-number-input"
              />
            </div>

            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <button className="popover-save-btn" style={{ flex: 1 }} onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : saved ? "Saved!" : "Save"}
              </button>
              <button
                className="popover-save-btn"
                style={{ flex: 0, background: "rgba(224,108,117,0.15)", color: "#e06c75" }}
                onClick={handleReset}
              >
                Reset
              </button>
            </div>
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* System Prompt (Primary) */}
          <div
            style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", userSelect: "none" }}
            onClick={() => setPromptExpanded(!promptExpanded)}
          >
            {promptExpanded ? "\u25BE" : "\u25B8"} System Prompt (personality)
          </div>
          {promptExpanded && (
            <div className="model-system-prompt-block">
              {prompts.primary || "Not found."}
            </div>
          )}

          {/* System Prompt (Sidecar) */}
          <div
            style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", userSelect: "none" }}
            onClick={() => setSidecarExpanded(!sidecarExpanded)}
          >
            {sidecarExpanded ? "\u25BE" : "\u25B8"} System Prompt (sidecar persona)
          </div>
          {sidecarExpanded && (
            <div className="model-system-prompt-block">
              {prompts.sidecar || "Not found."}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
