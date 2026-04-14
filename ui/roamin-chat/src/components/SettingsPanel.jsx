import React, { useState, useEffect } from "react";
// Use the Tauri v2 global rather than requiring @tauri-apps/api package
const _tauriInvoke = window.__TAURI__?.core?.invoke ?? window.__TAURI__?.tauri?.invoke ?? null;
import {
  getSettings,
  getModels,
  selectModel,
  setVolume,
  setScreenshots as apiSetScreenshots,
} from "../apiClient";

/**
 * Slide-over settings panel (right edge).
 * Replaces the old inline settings-panel that was bolted below the header.
 *
 * @param {Function} onClose
 * @param {string}   selectedModel   - lifted state from App
 * @param {Function} onModelChange   - lifted setter
 * @param {Array}    models          - lifted models array from App
 */
export default function SettingsPanel({ onClose, selectedModel, onModelChange, models }) {
  const [volume, setVolumeState] = useState(100);
  const [screenshots, setScreenshotsState] = useState(true);
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const [modelSearch, setModelSearch] = useState("");

  // Load current settings on open
  useEffect(() => {
    getSettings().then((s) => {
      if (s.volume !== undefined) setVolumeState(Math.round(s.volume * 100));
      if (s.screenshots_enabled !== undefined) setScreenshotsState(s.screenshots_enabled);
    }).catch(() => {});
  }, []);

  const handleVolume = (val) => {
    setVolumeState(val);
    setVolume(val / 100).catch(() => {});
  };

  const handleScreenshots = (checked) => {
    setScreenshotsState(checked);
    apiSetScreenshots(checked).catch(() => {});
  };

  const handleAlwaysOnTop = (checked) => {
    setAlwaysOnTop(checked);
    if (_tauriInvoke) {
      _tauriInvoke("set_always_on_top", { onTop: checked }).catch(() => {});
    }
  };

  const filteredModels = models.filter((m) => {
    const name = (m.name || m.id || m).toLowerCase();
    return name.includes(modelSearch.toLowerCase());
  });

  return (
    <>
      <div className="overlay-backdrop" onClick={onClose} />
      <div className="settings-slide">
        <div className="sidebar-header">
          <span>Settings</span>
          <button className="sidebar-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="sidebar-body">
          {/* ── Model ── */}
          <div className="settings-section-title">Model</div>
          {models.length > 8 && (
            <input
              className="model-search"
              type="text"
              placeholder="Filter models…"
              value={modelSearch}
              onChange={(e) => setModelSearch(e.target.value)}
            />
          )}
          <div
            className={`model-option ${!selectedModel ? "selected" : ""}`}
            onClick={() => onModelChange("")}
          >
            <span className="model-checkmark">{!selectedModel ? "✓" : ""}</span>
            Auto
          </div>
          {filteredModels.map((m) => {
            const id = m.id || m;
            const name = m.name || m.id || m;
            return (
              <div
                key={id}
                className={`model-option ${selectedModel === id ? "selected" : ""}`}
                onClick={() => { onModelChange(id); selectModel(id).catch(() => {}); }}
              >
                <span className="model-checkmark">{selectedModel === id ? "✓" : ""}</span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {name}
                </span>
              </div>
            );
          })}

          <div className="settings-divider" />

          {/* ── Audio ── */}
          <div className="settings-section-title">Audio</div>
          <div className="settings-row" style={{ padding: "6px 14px" }}>
            <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              TTS Volume: {volume}%
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={volume}
              onChange={(e) => handleVolume(Number(e.target.value))}
              style={{ width: 100, accentColor: "var(--accent)" }}
            />
          </div>

          <div className="settings-divider" />

          {/* ── Context ── */}
          <div className="settings-section-title">Context</div>
          <div className="settings-row" style={{ padding: "6px 14px" }}>
            <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>Screenshots</label>
            <input
              type="checkbox"
              checked={screenshots}
              onChange={(e) => handleScreenshots(e.target.checked)}
              style={{ accentColor: "var(--accent)" }}
            />
          </div>

          <div className="settings-divider" />

          {/* ── App ── */}
          <div className="settings-section-title">App</div>
          <div className="theme-toggle-row">
            <span>Always on Top</span>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={alwaysOnTop}
                onChange={(e) => handleAlwaysOnTop(e.target.checked)}
              />
              <span className="slider" />
            </label>
          </div>
        </div>
      </div>
    </>
  );
}
