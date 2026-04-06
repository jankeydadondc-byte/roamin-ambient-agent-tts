import { useState } from "react";
import { installPlugin, validatePluginManifest } from "../apiClient";
import CapabilityHints from "./CapabilityHints";

export default function PluginActions({ onInstalled }) {
    const [id, setId] = useState('pkg.example');
    const [name, setName] = useState('Example Plugin');
    const [entrypoint, setEntrypoint] = useState('run.py');
    const [task, setTask] = useState(null);
    const [busy, setBusy] = useState(false);
    const [confirmationVisible, setConfirmationVisible] = useState(false);
    const [manifestPreview, setManifestPreview] = useState(null);
    const [lastPayload, setLastPayload] = useState(null);

    const valid = id && id.trim().length > 0;

    const submit = async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        try {
            const payload = { id, name, manifest: { id, name, entrypoint } };
            // Validate manifest first
            const validation = await validatePluginManifest(payload.manifest);
            if (!validation || validation.valid === false) {
                const missing = (validation && validation.missing) ? validation.missing.join(', ') : '';
                alert('Manifest validation failed. Missing: ' + missing);
                return;
            }

            // Show confirmation UI with manifest details and capability hints
            setManifestPreview(payload.manifest);
            setLastPayload(payload);
            setConfirmationVisible(true);
        } catch (err) {
            console.error(err);
            alert('Validation failed: ' + (err.message || err));
        } finally {
            setBusy(false);
        }
    };

    const cancelConfirm = () => {
        setConfirmationVisible(false);
        setManifestPreview(null);
        setLastPayload(null);
    };

    const confirmInstall = async () => {
        if (!lastPayload) return;
        setBusy(true);
        try {
            const res = await installPlugin(lastPayload);
            setTask(res.task_id || res.taskId || 'unknown');
            setConfirmationVisible(false);
            setManifestPreview(null);
            // let parent know to refresh after short delay and pass installed id
            setTimeout(() => onInstalled && onInstalled(lastPayload.id), 1400);
        } catch (err) {
            console.error(err);
            alert('Install failed: ' + (err.message || err));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div style={{ marginTop: 12 }} className="vscode-card">
            <h3>Plugin Actions</h3>
            {!confirmationVisible && (
                <form onSubmit={submit} aria-label="Install plugin">
                    <div style={{ marginBottom: 8 }}>
                        <label htmlFor="plugin-id">Id:</label>
                        <input id="plugin-id" className="vscode-input" value={id} onChange={(e) => setId(e.target.value)} aria-required />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                        <label htmlFor="plugin-name">Name:</label>
                        <input id="plugin-name" className="vscode-input" value={name} onChange={(e) => setName(e.target.value)} />
                    </div>
                    <div style={{ marginBottom: 8 }}>
                        <label htmlFor="plugin-entry">Entrypoint:</label>
                        <input id="plugin-entry" className="vscode-input" value={entrypoint} onChange={(e) => setEntrypoint(e.target.value)} />
                    </div>
                    <div style={{ marginTop: 8 }}>
                        <button className="vscode-button" type="submit" disabled={busy || !valid}>{busy ? 'Validating…' : 'Install'}</button>
                    </div>
                    {task && <div style={{ marginTop: 8 }}>Install task: {task}</div>}
                </form>
            )}

            {confirmationVisible && manifestPreview && (
                <div style={{ marginTop: 8 }} aria-live="polite">
                    <h4>Confirm plugin installation</h4>
                    <div><strong>ID:</strong> <span style={{ fontFamily: 'monospace' }}>{manifestPreview.id}</span></div>
                    <div><strong>Name:</strong> {manifestPreview.name}</div>
                    <div><strong>Entrypoint:</strong> {manifestPreview.entrypoint}</div>
                    <div style={{ marginTop: 8 }}>
                        <strong>Requested capabilities:</strong>
                        <CapabilityHints capabilities={manifestPreview.requestedCapabilities || []} />
                    </div>
                    <div style={{ marginTop: 12 }}>
                        <button className="vscode-button" onClick={confirmInstall} disabled={busy}>{busy ? 'Installing…' : 'Confirm and Install'}</button>
                        <button className="vscode-small-button" onClick={cancelConfirm} style={{ marginLeft: 8 }}>Cancel</button>
                    </div>
                </div>
            )}
        </div>
    );
}
