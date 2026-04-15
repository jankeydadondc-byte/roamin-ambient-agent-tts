import React, { useState } from "react";
import AgentPicker from "./popovers/AgentPicker";
import ToolPicker from "./popovers/ToolPicker";
import PermissionToggle from "./popovers/PermissionToggle";
import ProjectPicker from "./popovers/ProjectPicker";
import ContextPicker from "./popovers/ContextPicker";
import PopoverBackdrop from "./PopoverBackdrop";
import { refreshModels } from "../apiClient";

/**
 * Bottom toolbar row beneath the textarea.
 * Props are all lifted state so parent (Chat) owns the values.
 */
export default function InputToolbar({
  models,
  selectedModel,
  onModelChange,
  agentMode,
  onAgentModeChange,
  permission,
  onPermissionChange,
  projectPath,
  onProjectPathChange,
  contextAttachment,
  onContextAttachmentChange,
  onOpenModelSidebar,
  onModelsRefresh,
}) {
  const [openPopover, setOpenPopover] = useState(null); // "context"|"agent"|"tools"|"permission"|"project"|"model"
  const [selectingModel, setSelectingModel] = useState(null); // model id currently loading
  const [refreshing, setRefreshing] = useState(false);

  const closePopover = () => setOpenPopover(null);

  const toggle = (name) => setOpenPopover((cur) => (cur === name ? null : name));

  const modelLabel = selectingModel
    ? "Loading…"
    : selectedModel
      ? (visibleModels.find((m) => (m.id || m) === selectedModel)?.name || selectedModel).slice(0, 20)
      : "Auto";

  const permIcons = { default: "🔒", bypass: "🔓", autopilot: "⚡" };

  const handleModelSelect = (id) => {
    setSelectingModel(id || "auto");
    setOpenPopover(null);
    // onModelChange (from App.jsx) handles both state + API call + localStorage persistence
    onModelChange(id);
    // Brief visual loading state then clear
    setTimeout(() => setSelectingModel(null), 800);
  };

  const handleRefreshModels = async () => {
    setRefreshing(true);
    try {
      const result = await refreshModels();
      if (result.models && onModelsRefresh) {
        onModelsRefresh(result.models);
      }
    } catch (_) {}
    finally {
      setRefreshing(false);
    }
  };

  // Filter out llama_cpp models whose file is missing (status === unavailable)
  const visibleModels = models.filter(
    (m) => !(m.provider === "llama_cpp" && m.status === "unavailable")
  );

  return (
    <div className="input-toolbar">
      {openPopover && <PopoverBackdrop onClose={closePopover} />}
      {/* Add Context */}
      <div className="popover-wrapper">
        <button
          className={`toolbar-btn ${contextAttachment ? "active" : ""}`}
          title="Add context"
          onClick={() => toggle("context")}
        >
          {contextAttachment ? "📎" : "+"}
        </button>
        {openPopover === "context" && (
          <ContextPicker
            value={contextAttachment}
            onChange={onContextAttachmentChange}
            onClose={() => setOpenPopover(null)}
          />
        )}
      </div>

      {/* Agent mode */}
      <div className="popover-wrapper">
        <button
          className={`toolbar-btn ${agentMode && agentMode !== "auto" ? "active" : ""}`}
          title="Select agent mode"
          onClick={() => toggle("agent")}
        >
          @
        </button>
        {openPopover === "agent" && (
          <AgentPicker
            value={agentMode}
            onChange={onAgentModeChange}
            onClose={() => setOpenPopover(null)}
          />
        )}
      </div>

      {/* Configure tools */}
      <div className="popover-wrapper">
        <button
          className="toolbar-btn"
          title="Configure tools"
          onClick={() => toggle("tools")}
        >
          ⚙
        </button>
        {openPopover === "tools" && (
          <ToolPicker onClose={() => setOpenPopover(null)} />
        )}
      </div>

      {/* Permissions */}
      <div className="popover-wrapper">
        <button
          className={`toolbar-btn ${permission !== "default" ? "active" : ""}`}
          title={`Permissions: ${permission}`}
          onClick={() => toggle("permission")}
        >
          {permIcons[permission] || "🔒"}
        </button>
        {openPopover === "permission" && (
          <PermissionToggle
            value={permission}
            onChange={onPermissionChange}
            onClose={() => setOpenPopover(null)}
          />
        )}
      </div>

      {/* Session target / project */}
      <div className="popover-wrapper">
        <button
          className={`toolbar-btn ${projectPath ? "active" : ""}`}
          title={projectPath ? `Target: ${projectPath}` : "Set session target"}
          onClick={() => toggle("project")}
        >
          📁
        </button>
        {openPopover === "project" && (
          <ProjectPicker
            value={projectPath}
            onChange={onProjectPathChange}
            onClose={() => setOpenPopover(null)}
          />
        )}
      </div>

      <div className="toolbar-spacer" />

      {/* Model pill */}
      <div
        className={`model-pill ${selectingModel ? "model-pill-loading" : ""}`}
        title="Switch model (right-click for settings)"
        onClick={() => !selectingModel && toggle("model")}
        onContextMenu={(e) => { e.preventDefault(); onOpenModelSidebar?.(); }}
      >
        {selectingModel ? "⟳ " : ""}{modelLabel} {!selectingModel && "▾"}
        {openPopover === "model" && (
          <div
            className="popover"
            style={{ right: 0, left: "auto", minWidth: 220 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="popover-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Model</span>
              <button
                className="toolbar-btn"
                title={refreshing ? "Refreshing…" : "Refresh from LM Studio"}
                onClick={(e) => { e.stopPropagation(); handleRefreshModels(); }}
                disabled={refreshing}
                style={{ fontSize: 12, padding: "1px 5px" }}
              >
                {refreshing ? "…" : "↺"}
              </button>
            </div>
            <div
              className={`model-option ${!selectedModel ? "selected" : ""}`}
              onClick={() => handleModelSelect("")}
            >
              <span className="model-checkmark">{!selectedModel ? "✓" : ""}</span>
              Auto
            </div>
            {visibleModels.map((m) => {
              const id = m.id || m;
              const name = m.name || m.id || m;
              return (
                <div
                  key={id}
                  className={`model-option ${selectedModel === id ? "selected" : ""}`}
                  onClick={() => handleModelSelect(id)}
                  title={name}
                >
                  <span className="model-checkmark">{selectedModel === id ? "✓" : ""}</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {name}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
