import { useState } from "react";
import { pluginAction, uninstallPlugin } from "../apiClient";

export default function PluginDetail({ plugin, onUpdated }) {
    const [busy, setBusy] = useState(false);

    if (!plugin) return <div>Select a plugin to see details.</div>;

    const enable = async () => {
        setBusy(true);
        try {
            await pluginAction(plugin.id, 'enable');
            onUpdated && onUpdated();
        } catch (e) {
            console.error(e);
        } finally {
            setBusy(false);
        }
    };

    const disable = async () => {
        setBusy(true);
        try {
            await pluginAction(plugin.id, 'disable');
            onUpdated && onUpdated();
        } catch (e) {
            console.error(e);
        } finally {
            setBusy(false);
        }
    };

    const remove = async () => {
        if (!confirm(`Uninstall plugin ${plugin.name}?`)) return;
        setBusy(true);
        try {
            await uninstallPlugin(plugin.id);
            onUpdated && onUpdated();
        } catch (e) {
            console.error(e);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="vscode-card" role="region" aria-label={`Details for ${plugin.name}`}>
            <h3>{plugin.name}</h3>
            <div><strong>ID:</strong> <span style={{ fontFamily: 'monospace' }}>{plugin.id}</span></div>
            <div><strong>Enabled:</strong> {plugin.enabled ? 'yes' : 'no'}</div>
            <div style={{ marginTop: 8 }}>
                <button className="vscode-small-button" onClick={enable} disabled={busy || plugin.enabled} aria-disabled={busy || plugin.enabled}>Enable</button>
                <button className="vscode-small-button" onClick={disable} disabled={busy || !plugin.enabled} aria-disabled={busy || !plugin.enabled} style={{ marginLeft: 8 }}>Disable</button>
                <button className="vscode-small-button" onClick={remove} disabled={busy} aria-disabled={busy} style={{ marginLeft: 8 }}>Uninstall</button>
            </div>
        </div>
    );
}
