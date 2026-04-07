import { useEffect, useRef, useState } from "react";
import { connectEvents, getModels, getPlugins, getStatus, getTaskHistory } from "./apiClient";
import Header from "./components/Header";
import ModelSelect from "./components/ModelSelect";
import PluginActions from "./components/PluginActions";
import PluginDetail from "./components/PluginDetail";
import PluginList from "./components/PluginList";
import Sidebar from "./components/Sidebar";
import Supervisor from "./components/Supervisor";
import TaskHistory from "./components/TaskHistory";

// ==========================================
// Main App Component
// Accessible Roamin Control Panel
// ==========================================
export default function App() {
    const [status, setStatus] = useState(null);
    const [models, setModels] = useState([]);
    const [plugins, setPlugins] = useState([]);
    const [logs, setLogs] = useState([]);
    const [taskHistory, setTaskHistory] = useState([]);
    const [selected, setSelected] = useState(null);
    const [selectedModel, setSelectedModel] = useState(null);
    const wsRef = useRef(null);

    // ==========================================
    // Refresh plugins when status changes
    // ==========================================
    const refreshPlugins = async () => {
        try {
            const p = await getPlugins();
            setPlugins(p.plugins || []);
        } catch (e) {
            console.error("Failed to refresh plugins:", e);
        }
    };

    // ==========================================
    // Initialize on mount - load all state
    // ==========================================
    useEffect(() => {
        (async () => {
            try {
                const s = await getStatus();
                setStatus(s);
            } catch (e) {
                console.error("Failed to get status:", e);
                setStatus({ error: "Unable to reach control API (is it running?)", version: null });
            }

            try {
                const m = await getModels();
                setModels(m.models || []);
            } catch (e) {
                console.error("Failed to get models:", e);
            }

            await refreshPlugins();

            try {
                const th = await getTaskHistory();
                setTaskHistory(th.tasks || th || []);
            } catch (e) {
                console.error("Failed to get task history:", e);
            }
        })();

        // Setup WebSocket connection for live updates
        const ws = connectEvents((evt) => {
            try {
                if (evt && evt.type === 'plugin_event') {
                    refreshPlugins();
                }
                if (evt && (evt.type === 'task_update' || evt.type === 'task')) {
                    const t = evt.data || evt.task || null;
                    if (t && t.task_id) {
                        setTaskHistory((old) => {
                            const found = (old || []).some((o) => o.task_id === t.task_id);
                            if (found) return (old || []).map((o) => o.task_id === t.task_id ? { ...o, ...t } : o);
                            return [t, ...(old || [])].slice(0, 200);
                        });
                    }
                }
            } catch (e) {
                console.error("Event handler error:", e);
            }

            setLogs((l) => [JSON.stringify(evt), ...l].slice(0, 200));
        });

        wsRef.current = ws;
        return () => {
            if (wsRef.current && wsRef.current.close) {
                wsRef.current.close();
            }
        };
    }, []);

    // ==========================================
    // Navigation helper - smooth scroll to section
    // ==========================================
    const navigateTo = (id) => {
        const el = document.getElementById(id);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Ensure element is focusable for keyboard users
            const focusable = el.querySelector('button, input, select, [tabindex]');
            if (focusable) focusable.focus();
        }
    };

    // ==========================================
    // Filter logs for specific plugin
    // ==========================================
    const filterLogsFor = (pluginId) => {
        return logs
            .map((l) => {
                try { return JSON.parse(l); } catch (e) { return null; }
            })
            .filter(Boolean)
            .filter((o) => (o.data && o.data.plugin_id && o.data.plugin_id === pluginId) ||
                          (o.type === 'plugin_event' && o.data && o.data.plugin_id === pluginId))
            .map((o) => JSON.stringify(o));
    };

    // ==========================================
    // Render the accessible layout
    // ==========================================
    return (
        <div className="vscode-workbench" role="main">
            <Header status={status} />

            <section className="vscode-layout" aria-label="Control Panel Main Layout">
                {/* Sidebar Navigation */}
                <Sidebar
                    onNavigate={navigateTo}
                    workspace="local"
                    onWorkspaceChange={() => { }}
                    selectedSection={null}
                    setSelectedSection={() => { }}
                />

                <div className="vscode-main">
                    {/* Left Column - Model & History Controls */}
                    <div className="vscode-left" aria-label="Control Options">
                        <section id="models" aria-labelledby="models-heading">
                            <h3 id="models-heading">Models</h3>
                            <ModelSelect
                                models={models}
                                value={selectedModel}
                                onSelect={(m) => setSelectedModel(m)}
                            />
                            <div
                                style={{ marginTop: 8, fontSize: 13, color: '#9d9d9d' }}
                                aria-live="polite"
                            >
                                Selected model: {selectedModel ? `${selectedModel.name} — ${selectedModel.status}` : 'None'}
                            </div>
                        </section>

                        <section id="task-history" style={{ marginTop: 12 }} aria-labelledby="task-history-heading">
                            <h3 id="task-history-heading">Task History</h3>
                            <TaskHistory tasks={taskHistory} />
                        </section>

                        <section id="plugins" style={{ marginTop: 12 }} aria-labelledby="plugins-heading">
                            <h3 id="plugins-heading">Plugins</h3>
                            <PluginList
                                plugins={plugins}
                                value={selected}
                                onSelect={(p) => setSelected(p)}
                                onRefresh={() => refreshPlugins()}
                            />

                            <div id="plugin-actions" aria-label="Plugin installation actions">
                                <PluginActions
                                    onInstalled={async (id) => {
                                        await refreshPlugins();
                                        try {
                                            const latest = await getPlugins();
                                            const p = (latest.plugins || []).find((pl) => pl.id === id) || null;
                                            if (p) setSelected(p);
                                        } catch (e) {
                                            // ignore errors silently
                                        }
                                    }}
                                />
                            </div>
                        </section>
                    </div>

                    {/* Right Column - Logs & Supervisor */}
                    <div className="vscode-right" aria-label="Monitoring Panel">
                        <section id="logs" aria-labelledby="logs-heading">
                            <h3 id="logs-heading">Live Events</h3>
                            <div
                                className="logs"
                                role="log"
                                aria-live="polite"
                                aria-relevant="additions text"
                            >
                                {logs.length ? (
                                    logs.map((l, i) => (
                                        <div key={i} style={{ fontFamily: "monospace", fontSize: 12 }}>
                                            {l}
                                        </div>
                                    ))
                                ) : (
                                    <div style={{ color: "#888" }}>No events yet</div>
                                )}
                            </div>
                        </section>

                        <section id="supervisor" style={{ marginTop: 12 }} aria-labelledby="supervisor-heading">
                            <h3 id="supervisor-heading">Supervisor</h3>
                            <div className="vscode-card">
                                <Supervisor plugins={plugins} onUpdated={() => refreshPlugins()} />
                            </div>
                        </section>

                        <section id="plugin-logs" style={{ marginTop: 12 }} aria-labelledby="plugin-logs-heading">
                            <h3 id="plugin-logs-heading">Plugin Logs</h3>
                            <div className="vscode-card">
                                <div className="plugin-logs">
                                    {plugins.length ? (
                                        plugins.map((p) => (
                                            <details key={p.id} style={{ marginBottom: 8 }}>
                                                <summary style={{ cursor: "pointer" }}>{p.id} — recent events</summary>
                                                <div style={{ fontFamily: "monospace", fontSize: 12, marginTop: 6 }}>
                                                    {filterLogsFor(p.id).length ? (
                                                        filterLogsFor(p.id).map((l, i) => <div key={i}>{l}</div>)
                                                    ) : (
                                                        <div style={{ color: "#888" }}>No events for this plugin</div>
                                                    )}
                                                </div>
                                            </details>
                                        ))
                                    ) : (
                                        <div style={{ color: "#888" }}>No plugins installed</div>
                                    )}
                                </div>
                            </div>
                        </section>

                        <section id="plugin-detail" style={{ marginTop: 12 }} aria-labelledby="plugin-detail-heading">
                            <h3 id="plugin-detail-heading">Plugin Details</h3>
                            <div className="vscode-card">
                                <PluginDetail plugin={selected} onUpdated={() => refreshPlugins()} />
                            </div>
                        </section>
                    </div>
                </div>
            </section>
        </div>
    );
}
