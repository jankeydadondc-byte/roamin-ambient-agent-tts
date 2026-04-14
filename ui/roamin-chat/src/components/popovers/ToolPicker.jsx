import React, { useEffect, useState } from "react";
import { getTools } from "../../apiClient";

/**
 * Popover showing all registered agent tools (read-only in v1).
 */
export default function ToolPicker({ onClose }) {
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTools()
      .then((d) => setTools(d.tools || []))
      .catch(() => setTools([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="popover" style={{ minWidth: 230 }}>
      <div className="popover-title">Available Tools</div>
      {loading && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
          Loading…
        </div>
      )}
      <div className="tool-list-scroll">
        {tools.map((t) => (
          <div key={t.name} className="tool-row">
            <span className="tool-row-name">{t.name}</span>
            <span className={`popover-risk-badge risk-${t.risk}`}>{t.risk}</span>
          </div>
        ))}
      </div>
      {!loading && tools.length === 0 && (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
          No tools available.
        </div>
      )}
      <div style={{ padding: "6px 12px 8px", fontSize: 10, color: "var(--text-secondary)", borderTop: "1px solid var(--border)" }}>
        Tool toggle coming in v2.
      </div>
    </div>
  );
}
