import React, { useState, useEffect, useRef } from "react";
import AgentPicker from "./popovers/AgentPicker";
import ToolPicker from "./popovers/ToolPicker";
import PermissionToggle from "./popovers/PermissionToggle";
import ProjectPicker from "./popovers/ProjectPicker";
import ContextPicker from "./popovers/ContextPicker";
import { selectModel, refreshModels } from "../apiClient";

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

  // Close popover on outside click
  const toolbarRef = useRef(null);
  useEffect(() => {
    if (!openPopover) return;
    const handler = (e) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target)) {
        setOpenPopover(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openPopover]);

  const toggle = (name) => setOpenPopover((cur) => (cur === name ? null : name));

  const modelLabel = selectingModel
    ? "Loading…"
    : selectedModel
      ? (models.find((m) => (m.id || m) === selectedModel)?.name || selectedModel).slice(0, 20)
      : "Auto";

  const permIcons = { default: "🔒", bypass: "🔓", autopilot: "⚡" };

  const handleModelSelect = async (id) => {
    setSelectingModel(id || "auto");
    setOpenPopover(null);
    try {
      onModelChange(id);
      await selectModel(id);
    } catch (_) {}
    finally {
      setSelectingModel(null);
    }
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

  return (
    <div className="input-toolbar" ref={toolbarRef}>
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
            {models.map((m) => {
              const id = m.id || m;
              const name = m.name || m.id || m;
              const isUnavailable = m.status === "unavailable";
              return (
                <div
                  key={id}
                  className={`model-option ${selectedModel === id ? "selected" : ""} ${isUnavailable ? "model-unavailable" : ""}`}
                  onClick={() => !isUnavailable && handleModelSelect(id)}
                  title={isUnavailable ? "Not available in LM Studio" : name}
                >
                  <span className="model-checkmark">{selectedModel === id ? "✓" : ""}</span>
                  <span style={{ opacity: isUnavailable ? 0.45 : 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {name}
                  </span>
                  {isUnavailable && (
                    <span style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: "auto", flexShrink: 0 }}>offline</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
