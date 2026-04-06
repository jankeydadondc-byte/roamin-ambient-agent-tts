import { useState } from "react";
import { pluginAction } from "../apiClient";

export default function Supervisor({ plugins = [], onUpdated }) {
    const [busy, setBusy] = useState(null);

    const handleEnableDisable = async (pluginId, action) => {
        setBusy(pluginId);
        try {
            await pluginAction(pluginId, action);
            onUpdated && onUpdated();
        } catch (e) {
            console.error(e);
            alert("Action failed: " + (e.message || e));
        } finally {
            setBusy(null);
        }
    };

    const handleRestart = async (plugin) => {
        setBusy(plugin.id);
        try {
            // Prototype restart: disable -> enable
            if (plugin.enabled) {
                await pluginAction(plugin.id, "disable");
                await new Promise((r) => setTimeout(r, 300));
                await pluginAction(plugin.id, "enable");
            } else {
                await pluginAction(plugin.id, "enable");
            }
            onUpdated && onUpdated();
        } catch (e) {
            console.error(e);
            alert("Restart failed: " + (e.message || e));
        } finally {
            setBusy(null);
        }
    };

    return (
        <div>
            <h3>Supervisor</h3>
            <div>
                <table className="vscode-table" style={{ width: "100%" }}>
                    <thead>
                        <tr>
                            <th style={{ textAlign: "left", padding: 6 }}>ID</th>
                            <th style={{ textAlign: "left", padding: 6 }}>Name</th>
                            <th style={{ textAlign: "left", padding: 6 }}>Status</th>
                            <th style={{ textAlign: "left", padding: 6 }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {plugins.map((p) => (
                            <tr key={p.id}>
                                <td style={{ padding: 6, fontFamily: "monospace" }}>{p.id}</td>
                                <td style={{ padding: 6 }}>{p.name}</td>
                                <td style={{ padding: 6 }}>{p.enabled ? "running" : "stopped"}</td>
                                <td style={{ padding: 6 }}>
                                    <button className="vscode-small-button" onClick={() => handleEnableDisable(p.id, p.enabled ? "disable" : "enable")} disabled={busy === p.id}>
                                        {p.enabled ? "Disable" : "Enable"}
                                    </button>
                                    <button className="vscode-small-button" style={{ marginLeft: 8 }} onClick={() => handleRestart(p)} disabled={busy === p.id}>
                                        Restart
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
