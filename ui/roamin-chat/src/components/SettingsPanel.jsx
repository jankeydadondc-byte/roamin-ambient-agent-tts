import React, { useState, useEffect } from "react";
// Lazy getter — Tauri v2 global isn't available until after WebView loads
const getTauriInvoke = () =>
  window.__TAURI__?.core?.invoke ?? window.__TAURI__?.tauri?.invoke ?? null;
import {
  getSettings,
  setVolume,
  setScreenshots as apiSetScreenshots,
  refreshModels,
  scanModels,
  updateSettings,
} from "../apiClient";

/**
 * Slide-over settings panel (right edge).
 * Replaces the old inline settings-panel that was bolted below the header.
 *
 * @param {Function} onClose
 * @param {string}   selectedModel   - lifted state from App
 * @param {Function} onModelChange   - lifted setter
 * @param {Array}    models          - lifted models array from App
 * @param {Function} onModelsRefresh - called with fresh models array after refresh
 */
export default function SettingsPanel({ onClose, selectedModel, onModelChange, models, onModelsRefresh }) {
  const [volume, setVolumeState] = useState(100);
  const [screenshots, setScreenshotsState] = useState(true);
  const [alwaysOnTop, setAlwaysOnTop] = useState(
    () => localStorage.getItem("alwaysOnTop") === "true"
  );
  const [modelSearch, setModelSearch] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [selectingModel, setSelectingModel] = useState(null); // model id being loaded

  // Option 1 agentic settings
  const [agenticMode, setAgenticModeState] = useState(false);
  const [planningModel, setPlanningModelState] = useState("");
  const [planningModelSearch, setPlanningModelSearch] = useState("");

  // Load current settings on open
  useEffect(() => {
    getSettings().then((s) => {
      if (s.volume !== undefined) setVolumeState(Math.round(s.volume * 100));
      if (s.screenshots_enabled !== undefined) setScreenshotsState(s.screenshots_enabled);
      if (s.always_on_top !== undefined) {
        setAlwaysOnTop(s.always_on_top);
        localStorage.setItem("alwaysOnTop", String(s.always_on_top));
      }
      if (s.agentic_mode !== undefined) setAgenticModeState(s.agentic_mode);
      if (s.planning_model !== undefined) setPlanningModelState(s.planning_model || "");
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
    localStorage.setItem("alwaysOnTop", String(checked));
    // Persist to backend
    updateSettings({ always_on_top: checked }).catch(() => {});
    // Apply to Tauri window
    const invoke = getTauriInvoke();
    if (invoke) {
      invoke("set_always_on_top", { onTop: checked }).catch(() => {});
    }
  };

  const handleAgenticMode = (checked) => {
    setAgenticModeState(checked);
    updateSettings({ agentic_mode: checked }).catch(() => {});
  };

  const handlePlanningModelSelect = (id) => {
    setPlanningModelState(id);
    updateSettings({ planning_model: id }).catch(() => {});
  };

  const handleModelSelect = (id) => {
    setSelectingModel(id);
    // onModelChange (from App.jsx) handles API call + localStorage persistence
    onModelChange(id);
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

  const handleScanModels = async () => {
    setScanning(true);
    try {
      const result = await scanModels();
      if (result.models && onModelsRefresh) {
        onModelsRefresh(result.models);
      }
    } catch (_) {}
    finally {
      setScanning(false);
    }
  };

  // Hide llama_cpp models whose file is missing
  const visibleModels = models.filter(
    (m) => !(m.provider === "llama_cpp" && m.status === "unavailable")
  );
  const filteredModels = visibleModels.filter((m) => {
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
          <div className="settings-section-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Model</span>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                className="toolbar-btn"
                title={scanning ? "Scanning…" : "Scan filesystem for GGUF models"}
                onClick={handleScanModels}
                disabled={scanning || refreshing}
                style={{ fontSize: 11, padding: "2px 7px" }}
              >
                {scanning ? "…" : "⊕ Scan"}
              </button>
              <button
                className="toolbar-btn"
                title={refreshing ? "Refreshing…" : "Refresh model list"}
                onClick={handleRefreshModels}
                disabled={refreshing || scanning}
                style={{ fontSize: 13, padding: "2px 6px" }}
              >
                {refreshing ? "…" : "↺"}
              </button>
            </div>
          </div>
          {visibleModels.length > 8 && (
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
            onClick={() => handleModelSelect("")}
          >
            <span className="model-checkmark">{!selectedModel ? "✓" : ""}</span>
            Auto
          </div>
          {filteredModels.map((m) => {
            const id = m.id || m;
            const name = m.name || m.id || m;
            const isLoading = selectingModel === id;
            const isUnavailable = m.status === "unavailable";
            return (
              <div
                key={id}
                className={`model-option ${selectedModel === id ? "selected" : ""} ${isUnavailable ? "model-unavailable" : ""}`}
                onClick={() => !isUnavailable && handleModelSelect(id)}
                title={isUnavailable ? "Not available in LM Studio" : name}
              >
                <span className="model-checkmark">
                  {isLoading ? "⟳" : selectedModel === id ? "✓" : ""}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", opacity: isUnavailable ? 0.45 : 1 }}>
                  {name}
                </span>
                {isUnavailable && (
                  <span style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: "auto", flexShrink: 0 }}>offline</span>
                )}
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

          <div className="settings-divider" />

          {/* ── Agentic Loop (Option 1) ── */}
          <div className="settings-section-title">Agentic Loop</div>
          <div className="theme-toggle-row" style={{ marginBottom: 4 }}>
            <span>Enable Agentic Mode</span>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={agenticMode}
                onChange={(e) => handleAgenticMode(e.target.checked)}
              />
              <span className="slider" />
            </label>
          </div>
          <p style={{ fontSize: 10, color: "var(--text-secondary)", padding: "0 14px 8px", margin: 0 }}>
            When on, Roamin plans tool use before answering. Use ⚡ in the input toolbar to override per message.
          </p>

          <div className="settings-section-title" style={{ fontSize: 11 }}>Planning Model</div>
          <p style={{ fontSize: 10, color: "var(--text-secondary)", padding: "0 14px 4px", margin: 0 }}>
            Model used for planning &amp; reflection. Recommended: same as chat model to avoid VRAM swap.
          </p>
          {visibleModels.length > 6 && (
            <input
              className="model-search"
              type="text"
              placeholder="Filter models…"
              value={planningModelSearch}
              onChange={(e) => setPlanningModelSearch(e.target.value)}
              style={{ margin: "2px 10px 4px" }}
            />
          )}
          <div
            className={`model-option ${!planningModel ? "selected" : ""}`}
            onClick={() => handlePlanningModelSelect("")}
            style={{ fontSize: 12 }}
          >
            <span className="model-checkmark">{!planningModel ? "✓" : ""}</span>
            Auto (best available)
          </div>
          {visibleModels
            .filter((m) => {
              if (!planningModelSearch) return true;
              const name = (m.name || m.id || m).toLowerCase();
              return name.includes(planningModelSearch.toLowerCase());
            })
            .map((m) => {
              const id = m.id || m;
              const name = m.name || m.id || m;
              return (
                <div
                  key={id}
                  className={`model-option ${planningModel === id ? "selected" : ""}`}
                  onClick={() => handlePlanningModelSelect(id)}
                  title={name}
                  style={{ fontSize: 12 }}
                >
                  <span className="model-checkmark">{planningModel === id ? "✓" : ""}</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {name}
                  </span>
                </div>
              );
            })}
        </div>
      </div>
    </>
  );
}
