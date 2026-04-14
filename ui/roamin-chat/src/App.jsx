import React, { useState, useEffect, useRef, useCallback } from "react";
import Chat from "./components/Chat";
import VolumeControl from "./components/VolumeControl";
import {
  getModels,
  selectModel,
  setScreenshots as apiSetScreenshots,
  connectEvents,
  onConnectionChange,
} from "./apiClient";

// Maps connection state → { color, label } for the status dot
const CONN_STYLES = {
  connecting:   { color: "#f5a623", label: "Connecting…" },
  connected:    { color: "#4caf50", label: "Connected" },
  disconnected: { color: "#e53935", label: "Disconnected" },
};

export default function App() {
  const [models, setModels]                   = useState([]);
  const [modelsLoading, setModelsLoading]     = useState(false);
  const [selectedModel, setSelectedModel]     = useState("");
  const [screenshotsEnabled, setScreenshotsEnabled] = useState(true);
  const [showSettings, setShowSettings]       = useState(false);
  const [connState, setConnState]             = useState("connecting");

  // Load (or reload) the model list whenever the connection becomes "connected".
  // This handles the race where the Tauri app starts before Roamin is ready:
  // the initial fetch fails/returns [], but once the WS reconnect fires and
  // the state becomes "connected" we pick up the real list.
  const loadModels = useCallback(() => {
    setModelsLoading(true);
    getModels()
      .then((data) => {
        setModels(data.models || []);
        // Pre-select the first model if nothing is selected yet
        if (!selectedModel && data.models && data.models.length > 0) {
          setSelectedModel(data.models[0].id || "");
        }
      })
      .catch(() => setModels([]))
      .finally(() => setModelsLoading(false));
  }, [selectedModel]);

  // Track previous connection state so we only reload on transitions to "connected"
  const prevConnState = useRef(null);

  useEffect(() => {
    const unsub = onConnectionChange((state) => {
      setConnState(state);

      // Reload models whenever we (re)connect
      if (state === "connected" && prevConnState.current !== "connected") {
        loadModels();
      }
      prevConnState.current = state;
    });

    // Also kick off an immediate model load in case we're already connected
    loadModels();

    // Connect to WebSocket for real-time events
    const conn = connectEvents((event) => {
      if (event.type === "chat_response") {
        // Handled in Chat component via its own state
      }
    });

    return () => {
      unsub();
      conn.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const connStyle = CONN_STYLES[connState] || CONN_STYLES.disconnected;

  return (
    <div className="app">
      <header className="header">
        <h1>Roamin</h1>
        <div className="header-controls">
          {/* Connection status dot */}
          <span
            title={connStyle.label}
            style={{
              display: "inline-block",
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: connStyle.color,
              marginRight: 6,
              flexShrink: 0,
              boxShadow:
                connState === "connected" ? `0 0 4px ${connStyle.color}` : "none",
              transition: "background 0.3s, box-shadow 0.3s",
            }}
          />

          {/* Model selector — shows once models are loaded, or a loading hint */}
          {modelsLoading ? (
            <span style={{ fontSize: 11, opacity: 0.5, marginRight: 6 }}>
              Loading…
            </span>
          ) : models.length > 0 ? (
            <select
              value={selectedModel}
              onChange={(e) => {
                const modelId = e.target.value;
                setSelectedModel(modelId);
                selectModel(modelId).catch((err) =>
                  console.error("[App] Model switch failed:", err)
                );
              }}
              title="Select model"
            >
              <option value="">Auto</option>
              {models.map((m) => (
                <option key={m.id || m} value={m.id || m}>
                  {m.name || m.id || m}
                </option>
              ))}
            </select>
          ) : connState === "disconnected" ? (
            <span
              style={{
                fontSize: 11,
                opacity: 0.6,
                marginRight: 4,
                cursor: "pointer",
                textDecoration: "underline",
              }}
              title="Retry connection"
              onClick={loadModels}
            >
              Retry
            </span>
          ) : null}

          <button
            onClick={() => setShowSettings(!showSettings)}
            title="Settings"
          >
            {showSettings ? "✕" : "⋯"}
          </button>
        </div>
      </header>

      <Chat />

      {showSettings && (
        <div className="settings-panel">
          <VolumeControl />
          <div className="settings-row">
            <label>Screenshots</label>
            <input
              type="checkbox"
              checked={screenshotsEnabled}
              onChange={(e) => {
                setScreenshotsEnabled(e.target.checked);
                apiSetScreenshots(e.target.checked).catch(() => {});
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
