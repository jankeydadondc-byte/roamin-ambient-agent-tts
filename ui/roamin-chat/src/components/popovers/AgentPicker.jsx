import React, { useEffect, useState } from "react";
import { getAgents, createAgent, getModels } from "../../apiClient";

/**
 * Popover for selecting agent mode — loads dynamically from GET /agents.
 * Also provides a "Create New Agent" form at the bottom.
 *
 * @param {string}   value    - current agent id
 * @param {Function} onChange - called with new agent id
 * @param {Function} onClose
 */
export default function AgentPicker({ value, onChange, onClose }) {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [models, setModels] = useState([]);

  // Form state for new agent
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [newModel, setNewModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    getAgents()
      .then((d) => setAgents(d.agents || []))
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
    getModels()
      .then((d) => setModels(d.models || []))
      .catch(() => setModels([]));
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) { setSaveError("Name is required"); return; }
    setSaving(true);
    setSaveError("");
    try {
      const created = await createAgent({
        name: newName.trim(),
        description: newDesc.trim(),
        system_prompt: newPrompt.trim(),
        model: newModel,
        tools: [],
        risk_level: "low",
      });
      // Refresh agent list and select the new one
      const fresh = await getAgents();
      setAgents(fresh.agents || []);
      onChange(created.id);
      setShowCreate(false);
      onClose();
    } catch (e) {
      setSaveError(e?.message || "Failed to create agent");
    } finally {
      setSaving(false);
    }
  };

  if (showCreate) {
    return (
      <div className="popover" style={{ minWidth: 260, maxHeight: 420, overflowY: "auto" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="popover-title" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Create Agent</span>
          <button
            onClick={() => setShowCreate(false)}
            style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 14 }}
          >←</button>
        </div>

        <div style={{ padding: "4px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>Name *</div>
          <input
            className="popover-path-input"
            type="text"
            placeholder="My Agent"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            autoFocus
          />
        </div>

        <div style={{ padding: "4px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>Description</div>
          <input
            className="popover-path-input"
            type="text"
            placeholder="What this agent does"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
          />
        </div>

        <div style={{ padding: "4px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>System Prompt</div>
          <textarea
            className="popover-path-input"
            placeholder="You are a helpful assistant..."
            value={newPrompt}
            onChange={(e) => setNewPrompt(e.target.value)}
            rows={3}
            style={{ resize: "vertical", fontFamily: "inherit", width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ padding: "4px 12px 8px" }}>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>Model (optional)</div>
          <select
            className="popover-path-input"
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            style={{ width: "100%" }}
          >
            <option value="">Auto</option>
            {models.map((m) => (
              <option key={m.id || m} value={m.id || m}>{m.name || m.id || m}</option>
            ))}
          </select>
        </div>

        {saveError && (
          <div style={{ padding: "0 12px 4px", fontSize: 11, color: "#e06c75" }}>{saveError}</div>
        )}

        <button className="popover-save-btn" onClick={handleCreate} disabled={saving}>
          {saving ? "Saving…" : "Save Agent"}
        </button>
      </div>
    );
  }

  return (
    <div className="popover" style={{ minWidth: 220 }} onMouseDown={(e) => e.stopPropagation()}>
      <div className="popover-title">Agent Mode</div>
      {loading && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>Loading…</div>
      )}
      {agents.map((a) => (
        <div
          key={a.id}
          className={`popover-option ${value === a.id ? "selected" : ""}`}
          onClick={() => { onChange(a.id); onClose(); }}
        >
          <span className="popover-option-check">{value === a.id ? "✓" : ""}</span>
          <div>
            <div>{a.name}</div>
            {a.description && (
              <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 1 }}>{a.description}</div>
            )}
          </div>
        </div>
      ))}
      {!loading && agents.length === 0 && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>No agents found.</div>
      )}
      <div
        className="popover-option"
        style={{ borderTop: "1px solid var(--border)", color: "var(--accent)" }}
        onClick={() => setShowCreate(true)}
      >
        <span className="popover-option-check">＋</span>
        <div>Create New Agent</div>
      </div>
    </div>
  );
}
