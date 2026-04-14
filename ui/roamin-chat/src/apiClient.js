/**
 * Roamin Chat API client — dynamic port discovery.
 *
 * Mirrors the Python-side ports.py logic:
 *   1. Check window.__CONTROL_API_URL__ (Tauri env override or user-set)
 *   2. Probe ports 8765-8775 in parallel for a live /status endpoint
 *   3. Cache the discovered URL; re-probe on network failure or after 30s
 *
 * Connection state ("connecting" | "connected" | "disconnected") is broadcast
 * via onConnectionChange() so the UI can render a live status indicator.
 */

// Ports to probe — must match agent/core/ports.py CONTROL_API_PORT_RANGE
const CANDIDATE_PORTS = Array.from({ length: 11 }, (_, i) => 8765 + i);
const PROBE_TIMEOUT_MS = 1500;
const CACHE_TTL_MS = 30_000; // re-probe after 30s of inactivity

// --- Connection state ---

let _baseUrl = null;           // cached discovered base URL, or null
let _connState = "connecting"; // "connecting" | "connected" | "disconnected"
let _lastDiscovery = 0;        // timestamp of last successful discovery
let _discoveryPromise = null;  // deduplicate concurrent discovery calls
const _listeners = new Set();

function _setState(state) {
  if (_connState === state) return;
  _connState = state;
  for (const fn of _listeners) {
    try { fn(state); } catch (_) {}
  }
}

/**
 * Subscribe to connection state changes.
 * The callback is invoked immediately with the current state.
 * Returns an unsubscribe function.
 */
export function onConnectionChange(fn) {
  _listeners.add(fn);
  fn(_connState); // fire immediately so UI reflects current state on mount
  return () => _listeners.delete(fn);
}

/** Read the current connection state without subscribing. */
export function getConnectionState() {
  return _connState;
}

// --- Port discovery ---

async function _probePort(port) {
  const url = `http://127.0.0.1:${port}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${url}/status`, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timer);
    if (res.ok) return url;
  } catch (_) {
    clearTimeout(timer);
  }
  return null;
}

async function _runDiscovery() {
  // Priority 1: explicit override (Tauri env injection or user-set global)
  const override =
    (typeof window !== "undefined" && window.__CONTROL_API_URL__) || null;
  if (override) {
    const base = override.replace(/\/$/, "");
    _baseUrl = base;
    _lastDiscovery = Date.now();
    _setState("connected");
    return base;
  }

  // Priority 2: probe all candidate ports in parallel for fast discovery
  const results = await Promise.all(CANDIDATE_PORTS.map(_probePort));
  const found = results.find(Boolean);

  if (found) {
    _baseUrl = found;
    _lastDiscovery = Date.now();
    _setState("connected");
    return found;
  }

  // Nothing found
  _setState("disconnected");
  throw new Error(
    `Roamin Control API not found on ports ${CANDIDATE_PORTS[0]}–${CANDIDATE_PORTS.at(-1)}. ` +
    "Is run_wake_listener.py running?"
  );
}

/** Invalidate the cached URL — forces a fresh probe next call. */
function _invalidateCache() {
  _baseUrl = null;
  _lastDiscovery = 0;
}

/**
 * Resolve the base URL, using cache when fresh, re-discovering otherwise.
 * Deduplicates concurrent callers so we only probe once at a time.
 */
async function resolveBase() {
  // Cache hit: URL known and fresh
  if (_baseUrl && Date.now() - _lastDiscovery < CACHE_TTL_MS) {
    return _baseUrl;
  }

  // Deduplicate: if discovery is already in flight, reuse that promise
  if (!_discoveryPromise) {
    _setState("connecting");
    _discoveryPromise = _runDiscovery().finally(() => {
      _discoveryPromise = null;
    });
  }
  return _discoveryPromise;
}

// Kick off discovery immediately on module load (eager — no blocking)
resolveBase().catch(() => {});

// --- Core fetch wrapper ---

async function _fetch(path, options = {}) {
  let base;
  try {
    base = await resolveBase();
  } catch (e) {
    throw new Error(
      "Roamin is not running. Start run_wake_listener.py first."
    );
  }

  let res;
  try {
    res = await fetch(`${base}${path}`, options);
  } catch (networkErr) {
    // Network error — control API may have moved ports; invalidate and rethrow
    _invalidateCache();
    _setState("disconnected");
    throw networkErr;
  }

  if (!res.ok) {
    if (res.status >= 500) _setState("disconnected");
    throw new Error(`HTTP ${res.status} on ${path}`);
  }

  _setState("connected");
  return res;
}

// --- Chat endpoints ---

/**
 * Send a chat message to Roamin.
 * @param {string} message
 * @param {boolean} includeScreen - whether to attach a screenshot
 * @param {AbortSignal|null} signal - optional AbortController signal for stop-generation
 * @param {object} extra - optional extra payload fields (contextAttachment, agentMode, etc.)
 */
export async function sendMessage(message, includeScreen = false, signal = null, extra = {}) {
  const fetchOptions = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, include_screen: includeScreen, ...extra }),
  };
  if (signal) fetchOptions.signal = signal;

  const res = await _fetch("/chat", fetchOptions);
  try {
    const data = await res.json();
    console.log("[apiClient] /chat response:", data);
    return data;
  } catch (e) {
    console.error("[apiClient] Failed to parse /chat response:", e);
    const text = await res.text();
    console.error("[apiClient] Response body was:", text);
    throw e;
  }
}

export async function getChatHistory(sessionId = null, limit = 50) {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  params.set("limit", String(limit));
  try {
    const res = await _fetch(`/chat/history?${params}`);
    return res.json();
  } catch (_) {
    return { exchanges: [], count: 0 };
  }
}

export async function resetChat() {
  const res = await _fetch("/chat/reset", { method: "POST" });
  return res.json();
}

// --- Settings endpoints ---

export async function getSettings() {
  try {
    const res = await _fetch("/settings");
    return res.json();
  } catch (_) {
    return {};
  }
}

export async function setVolume(volume) {
  const res = await _fetch("/settings/volume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ volume }),
  });
  return res.json();
}

export async function setScreenshots(enabled) {
  const res = await _fetch("/settings/screenshots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

// --- Models & Status ---

export async function getModels() {
  try {
    const res = await _fetch("/models");
    return res.json();
  } catch (_) {
    return { models: [] };
  }
}

export async function selectModel(modelId, task = "default") {
  const res = await _fetch("/models/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId || "", task }),
  });
  return res.json();
}

export async function getStatus() {
  const res = await _fetch("/status");
  return res.json();
}

/** Return the active model routing table from the backend. */
export async function getCurrentModel() {
  try {
    const res = await _fetch("/models/current");
    return res.json();
  } catch (_) {
    return {};
  }
}

/** List all registered agent tools with name, description, and risk level. */
export async function getTools() {
  try {
    const res = await _fetch("/tools");
    return res.json();
  } catch (_) {
    return { tools: [] };
  }
}

/** List all stored chat sessions for the history sidebar. */
export async function getSessions() {
  try {
    const res = await _fetch("/sessions");
    return res.json();
  } catch (_) {
    return { sessions: [], current_session_id: null };
  }
}

export async function getPendingNotifications() {
  try {
    const res = await _fetch("/chat/pending");
    return res.json();
  } catch (_) {
    return { messages: [] };
  }
}

/** Refresh the model list from LM Studio and reconcile with config. */
export async function refreshModels() {
  try {
    const res = await _fetch("/models/refresh", { method: "POST" });
    return res.json();
  } catch (_) {
    return { refreshed: false, models: [] };
  }
}

/** List all agent definition files from the agents/ folder. */
export async function getAgents() {
  try {
    const res = await _fetch("/agents");
    return res.json();
  } catch (_) {
    return { agents: [] };
  }
}

/** Create a new agent definition file. */
export async function createAgent(agentData) {
  const res = await _fetch("/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(agentData),
  });
  return res.json();
}

/** Enable or disable a tool by name. */
export async function toggleTool(toolName, enabled) {
  const res = await _fetch(`/tools/${encodeURIComponent(toolName)}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

// --- WebSocket events ---

export function connectEvents(onEvent) {
  let ws = null;
  let closed = false;
  let backoff = 500;

  const connect = async () => {
    if (closed) return;

    // Always re-probe on each WS connect attempt so we follow port changes
    let base;
    try {
      base = await resolveBase();
    } catch (_) {
      scheduleReconnect();
      return;
    }

    const wsUrl = base.replace(/^http/, "ws") + "/ws/events";

    try {
      ws = new WebSocket(wsUrl);
    } catch (_) {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      backoff = 500; // reset on successful connection
      _setState("connected");
    };

    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch (_) {
        onEvent({ type: "raw", data: m.data });
      }
    };

    ws.onerror = () => {
      _setState("disconnected");
    };

    ws.onclose = () => {
      if (!closed) {
        _invalidateCache(); // force re-probe on next reconnect attempt
        scheduleReconnect();
      }
    };
  };

  const scheduleReconnect = () => {
    if (closed) return;
    setTimeout(() => {
      backoff = Math.min(30_000, Math.floor(backoff * 1.5));
      connect();
    }, backoff);
  };

  connect();

  return {
    close() {
      closed = true;
      if (ws) {
        try { ws.close(); } catch (_) {}
      }
    },
  };
}
