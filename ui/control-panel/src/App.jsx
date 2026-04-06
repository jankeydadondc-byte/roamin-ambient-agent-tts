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

export default function App() {
    const [status, setStatus] = useState(null);
    const [models, setModels] = useState([]);
    const [plugins, setPlugins] = useState([]);
    const [logs, setLogs] = useState([]);
    const [taskHistory, setTaskHistory] = useState([]);
    const [selected, setSelected] = useState(null);
    const [selectedModel, setSelectedModel] = useState(null);
    const wsRef = useRef(null);

    const refreshPlugins = async () => {
        try {
            const p = await getPlugins();
            setPlugins(p.plugins || []);
        } catch (e) { }
    };

    useEffect(() => {
        (async () => {
            try {
                const s = await getStatus();
                setStatus(s);
            } catch (e) {
                setStatus({ error: "Unable to reach control API (is it running?)" });
            }

            try {
                const m = await getModels();
                setModels(m.models || []);
            } catch (e) { }

            await refreshPlugins();
            try {
                const th = await getTaskHistory();
                setTaskHistory(th.tasks || th || []);
            } catch (e) { }
        })();

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
            } catch (e) { }
            setLogs((l) => [JSON.stringify(evt), ...l].slice(0, 200));
        });

        wsRef.current = ws;
        return () => {
            if (wsRef.current && wsRef.current.close) wsRef.current.close();
        };
    }, []);

    const navigateTo = (id) => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const filterLogsFor = (pluginId) => {
        return logs
            .map((l) => {
                try { return JSON.parse(l); } catch (e) { return null; }
            })
            .filter(Boolean)
            .filter((o) => (o.data && o.data.plugin_id && o.data.plugin_id === pluginId) || (o.type === 'plugin_event' && o.data && o.data.plugin_id === pluginId))
            .map((o) => JSON.stringify(o));
    };

    return (
        <div className="vscode-workbench">
            <Header status={status} />

            <section className="vscode-layout">
                <Sidebar onNavigate={navigateTo} workspace={"local"} onWorkspaceChange={() => { }} selectedSection={null} setSelectedSection={() => { }} />

                <div className="vscode-main">
                    <div className="vscode-left">
                        <section id="models">
                            <h3>Models</h3>
                            <ModelSelect models={models} value={selectedModel} onSelect={(m) => setSelectedModel(m)} />
                            <div style={{ marginTop: 8, fontSize: 13, color: '#9d9d9d' }}>
                                Selected model: {selectedModel ? `${selectedModel.name} — ${selectedModel.status}` : 'None'}
                            </div>
                        </section>

                        <section id="task-history" style={{ marginTop: 12 }}>
                            <h3>Task History</h3>
                            <TaskHistory tasks={taskHistory} />
                        </section>

                        <section id="plugins" style={{ marginTop: 12 }}>
                            <h3>Plugins</h3>
                            <PluginList plugins={plugins} value={selected} onSelect={(p) => setSelected(p)} onRefresh={() => refreshPlugins()} />

                            <div id="plugin-actions">
                                <PluginActions onInstalled={async (id) => {
                                    await refreshPlugins();
                                    try {
                                        const latest = await getPlugins();
                                        const p = (latest.plugins || []).find((pl) => pl.id === id) || null;
                                        if (p) setSelected(p);
                                    } catch (e) {
                                        // ignore
                                    }
                                }} />
                            </div>
                        </section>
                    </div>

                    <div className="vscode-right">
                        <section id="logs">
                            <h3>Live Events / Logs</h3>
                            <div className="logs">
                                {logs.map((l, i) => (
                                    <div key={i} style={{ fontFamily: "monospace", fontSize: 12 }}>{l}</div>
                                ))}
                            </div>
                        </section>

                        <section id="supervisor" style={{ marginTop: 12 }}>
                            <h3>Supervisor</h3>
                            <div className="vscode-card">
                                <Supervisor plugins={plugins} onUpdated={() => refreshPlugins()} />
                            </div>
                        </section>

                        <section id="plugin-logs" style={{ marginTop: 12 }}>
                            <h3>Plugin Logs (per-plugin)</h3>
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

                        <section id="plugin-detail" style={{ marginTop: 12 }}>
                            <h3>Plugin Detail</h3>
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
