import React, { useState } from "react";

/**
 * Right-overlay panel showing code artifacts extracted from chat messages.
 * @param {Array<{id, language, code, label}>} artifacts
 * @param {Function} onClose
 */
export default function ArtifactsPanel({ artifacts = [], onClose }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const artifact = artifacts[activeIdx];

  const handleCopy = () => {
    if (!artifact) return;
    navigator.clipboard.writeText(artifact.code).catch(() => {});
  };

  const handleDownload = () => {
    if (!artifact) return;
    const ext = artifact.language || "txt";
    const blob = new Blob([artifact.code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `artifact.${ext}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="sidebar-overlay right" style={{ display: "flex", flexDirection: "column" }}>
        <div className="sidebar-header">
          <span>Artifacts</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>

        {artifacts.length === 0 ? (
          <div style={{ padding: "16px 12px", fontSize: 12, color: "var(--text-secondary)" }}>
            No artifacts yet. Code blocks over 20 lines will appear here.
          </div>
        ) : (
          <>
            <div className="artifacts-tabs">
              {artifacts.map((a, i) => (
                <div
                  key={a.id}
                  className={`artifact-tab ${i === activeIdx ? "active" : ""}`}
                  onClick={() => setActiveIdx(i)}
                >
                  {a.label || `Artifact ${i + 1}`}
                </div>
              ))}
            </div>

            <div className="artifact-actions">
              <button className="artifact-action-btn" onClick={handleCopy} title="Copy code">
                ⎘ Copy
              </button>
              <button className="artifact-action-btn" onClick={handleDownload} title="Download as file">
                ↓ Download
              </button>
              {artifact?.language && (
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-secondary)" }}>
                  {artifact.language}
                </span>
              )}
            </div>

            <pre className="artifact-code">{artifact?.code || ""}</pre>
          </>
        )}
      </div>
    </>
  );
}
