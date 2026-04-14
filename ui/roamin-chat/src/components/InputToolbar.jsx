import React, { useState, useEffect, useRef } from "react";
import AgentPicker from "./popovers/AgentPicker";
import ToolPicker from "./popovers/ToolPicker";
import PermissionToggle from "./popovers/PermissionToggle";
import ProjectPicker from "./popovers/ProjectPicker";
import ContextPicker from "./popovers/ContextPicker";

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
}) {
  const [openPopover, setOpenPopover] = useState(null); // "context"|"agent"|"tools"|"permission"|"project"|"model"

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

  const modelLabel = selectedModel
    ? (models.find((m) => (m.id || m) === selectedModel)?.name || selectedModel).slice(0, 20)
    : "Auto";

  const permIcons = { default: "🔒", bypass: "🔓", autopilot: "⚡" };

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
          className={`toolbar-btn ${agentMode !== "auto" ? "active" : ""}`}
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
        className="model-pill"
        title="Switch model (right-click for settings)"
        onClick={() => toggle("model")}
        onContextMenu={(e) => { e.preventDefault(); onOpenModelSidebar?.(); }}
      >
        {modelLabel} ▾
        {openPopover === "model" && (
          <div
            className="popover"
            style={{ right: 0, left: "auto", minWidth: 200 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="popover-title">Model</div>
            <div className="model-option selected" onClick={() => { onModelChange(""); setOpenPopover(null); }}>
              <span className="model-checkmark">{!selectedModel ? "✓" : ""}</span>
              Auto
            </div>
            {models.map((m) => {
              const id = m.id || m;
              const name = m.name || m.id || m;
              return (
                <div
                  key={id}
                  className={`model-option ${selectedModel === id ? "selected" : ""}`}
                  onClick={() => { onModelChange(id); setOpenPopover(null); }}
                >
                  <span className="model-checkmark">{selectedModel === id ? "✓" : ""}</span>
                  {name}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
