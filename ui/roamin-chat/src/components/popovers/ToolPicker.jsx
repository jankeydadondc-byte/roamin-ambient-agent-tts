import React, { useEffect, useState } from "react";
import { getTools, toggleTool } from "../../apiClient";

/**
 * Popover showing all registered agent tools with enable/disable toggles.
 */
export default function ToolPicker({ onClose }) {
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null); // tool name being toggled
  const [error, setError] = useState(null);

  useEffect(() => {
    getTools()
      .then((d) => setTools(d.tools || []))
      .catch(() => setTools([]))
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (toolName, currentEnabled) => {
    const newEnabled = !currentEnabled;
    setToggling(toolName);
    setError(null);

    // Optimistic update
    setTools((prev) =>
      prev.map((t) => (t.name === toolName ? { ...t, enabled: newEnabled } : t))
    );

    try {
      await toggleTool(toolName, newEnabled);
    } catch (e) {
      console.error("[ToolPicker] Toggle failed:", toolName, e);
      setError(`Failed to toggle ${toolName}`);
      // Revert on error
      setTools((prev) =>
        prev.map((t) => (t.name === toolName ? { ...t, enabled: currentEnabled } : t))
      );
    } finally {
      setToggling(null);
    }
  };

  return (
    <div className="popover" style={{ minWidth: 260 }}>
      <div className="popover-title">Available Tools</div>
      {loading && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
          Loading…
        </div>
      )}
      {error && (
        <div style={{ padding: "4px 12px", fontSize: 11, color: "#e06c75" }}>{error}</div>
      )}
      <div className="tool-list-scroll">
        {tools.map((t) => (
          <div key={t.name} className="tool-row" style={{ justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
              <span className={`tool-row-name ${t.enabled === false ? "tool-disabled" : ""}`}>
                {t.name}
              </span>
              <span className={`popover-risk-badge risk-${t.risk}`}>{t.risk}</span>
            </div>
            <label
              className="toggle-switch"
              style={{ flexShrink: 0, opacity: toggling === t.name ? 0.5 : 1 }}
              title={t.enabled !== false ? "Disable tool" : "Enable tool"}
            >
              <input
                type="checkbox"
                checked={t.enabled !== false}
                disabled={toggling === t.name}
                onChange={() => handleToggle(t.name, t.enabled !== false)}
              />
              <span className="slider" />
            </label>
          </div>
        ))}
      </div>
      {!loading && tools.length === 0 && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
          No tools available.
        </div>
      )}
    </div>
  );
}
