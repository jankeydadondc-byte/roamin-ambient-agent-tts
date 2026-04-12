// Discover control API port from .loom/control_api_port.json; fallback to 8765 (#85)
let DEFAULT_BASE = (typeof window !== 'undefined' && window.__CONTROL_API_URL__) || 'http://127.0.0.1:8765';

async function _discoverPort() {
    try {
        const r = await fetch('/loom/control_api_port.json');
        if (r.ok) {
            const { port } = await r.json();
            if (port) DEFAULT_BASE = `http://127.0.0.1:${port}`;
        }
    } catch {
        // Use default — .loom file not served or not present
    }
}
// Attempt discovery on module load; non-blocking
_discoverPort();

let API_KEY = null;

export function setApiKey(key) {
    API_KEY = key;
}

// Build auth header aligned with backend middleware expectation (#85)
function _authHeader() {
    return API_KEY ? { 'x-roamin-api-key': API_KEY } : {};
}

// WS status listeners (global)
const wsStatusListeners = [];
export function onWsStatus(fn) {
    if (typeof fn === 'function') wsStatusListeners.push(fn);
    return () => {
        const i = wsStatusListeners.indexOf(fn);
        if (i >= 0) wsStatusListeners.splice(i, 1);
    };
}
function notifyWsStatus(state) {
    wsStatusListeners.forEach((fn) => {
        try { fn(state); } catch (e) { }
    });
}

export async function getStatus() {
    const res = await fetch(`${DEFAULT_BASE}/status`);
    if (!res.ok) throw new Error('status fetch failed');
    return res.json();
}

export async function getModels() {
    const res = await fetch(`${DEFAULT_BASE}/models`);
    if (!res.ok) return { models: [] };
    return res.json();
}

export async function getPlugins() {
    const res = await fetch(`${DEFAULT_BASE}/plugins`);
    if (!res.ok) return { plugins: [] };
    return res.json();
}

export async function installPlugin(payload) {
    const res = await fetch(`${DEFAULT_BASE}/plugins/install`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, _authHeader()),
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('install failed');
    return res.json();
}

export async function pluginAction(pluginId, action) {
    const res = await fetch(`${DEFAULT_BASE}/plugins/${encodeURIComponent(pluginId)}/action`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, _authHeader()),
        body: JSON.stringify({ action }),
    });
    if (!res.ok) throw new Error('action failed');
    return res.json();
}

export async function uninstallPlugin(pluginId) {
    const res = await fetch(`${DEFAULT_BASE}/plugins/${encodeURIComponent(pluginId)}`, {
        method: 'DELETE',
        headers: _authHeader(),
    });
    if (!res.ok) throw new Error('uninstall failed');
    return res.json();
}

export async function validatePluginManifest(manifest) {
    const res = await fetch(`${DEFAULT_BASE}/plugins/validate`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, _authHeader()),
        body: JSON.stringify({ manifest }),
    });
    if (!res.ok) throw new Error('validate failed');
    return res.json();
}

export async function getTaskHistory({ page = 1, perPage = 20, status = null, taskType = null, since = null, q = null } = {}) {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(perPage));
    if (status) params.set('status', status);
    if (taskType) params.set('task_type', taskType);
    if (since) params.set('since', since);
    if (q) params.set('q', q);
    const res = await fetch(`${DEFAULT_BASE}/task-history?${params}`);
    if (!res.ok) return { tasks: [], total: 0, page: 1, per_page: perPage, pages: 1 };
    return res.json();
}

export function connectEvents(onEvent) {
    const baseWs = DEFAULT_BASE.replace('http', 'ws') + '/ws/events';
    let ws = null;
    let closed = false;
    let backoff = 500;

    const makeUrl = () => baseWs + (API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : '');

    const connect = () => {
        notifyWsStatus('connecting');
        try {
            ws = new WebSocket(makeUrl());
        } catch (e) {
            console.warn('WS connect failed', e);
            scheduleReconnect();
            return;
        }

        ws.onmessage = (m) => {
            try {
                const obj = JSON.parse(m.data);
                onEvent(obj);
            } catch (e) {
                onEvent({ type: 'raw', data: m.data });
            }
        };
        ws.onopen = () => {
            backoff = 500;
            notifyWsStatus('connected');
        };
        ws.onerror = () => { /* noop */ };
        ws.onclose = () => {
            notifyWsStatus('disconnected');
            if (!closed) scheduleReconnect();
        };
    };

    const scheduleReconnect = () => {
        setTimeout(() => {
            backoff = Math.min(30000, backoff * 1.5);
            connect();
        }, backoff);
    };

    connect();

    return {
        close() {
            closed = true;
            if (!ws) return;
            if (ws.readyState === WebSocket.CONNECTING) {
                // Defer close until connected to avoid browser-level error in React StrictMode.
                // Calling close() on a CONNECTING socket logs a native browser error even with try/catch.
                ws.onopen = () => { try { ws.close(); } catch (e) { } };
            } else {
                try { ws.close(); } catch (e) { }
            }
        }
    };
}
