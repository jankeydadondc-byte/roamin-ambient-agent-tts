

import { useEffect, useState } from "react";
import { onWsStatus, setApiKey } from "../apiClient";

export default function Header({ status }) {
    const ok = status && status.status === 'ok';
    const [key, setKey] = useState(() => {
        try { return window.localStorage.getItem('control_api_key') || ''; } catch (e) { return ''; }
    });

    const [wsStatus, setWsStatus] = useState('disconnected');

    useEffect(() => {
        if (key && key.length) setApiKey(key);
    }, [key]);

    useEffect(() => {
        const off = onWsStatus((s) => setWsStatus(s));
        return off;
    }, []);

    const save = () => {
        try { window.localStorage.setItem('control_api_key', key); } catch (e) { }
        setApiKey(key);
    };

    const clear = () => {
        setKey('');
        try { window.localStorage.removeItem('control_api_key'); } catch (e) { }
        setApiKey(null);
    };

    return (
        <div className="vscode-header">
            <div>
                <h1>Roamin Control — Prototype</h1>
                <div style={{ fontSize: 12, color: '#9d9d9d' }}>Local control panel</div>
            </div>

            <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 12 }}>
                    API: <span style={{ color: ok ? 'var(--vscode-accent)' : '#e04444' }}>{ok ? 'connected' : 'disconnected'}</span>
                </div>
                <div style={{ fontSize: 12, color: '#9d9d9d' }}>{status ? (ok ? `v${status.version}` : 'no status') : 'loading...'}</div>

                <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
                    <div style={{ fontSize: 12, marginRight: 8 }}>
                        WS: <span style={{ color: wsStatus === 'connected' ? 'var(--vscode-accent)' : (wsStatus === 'connecting' ? '#e7a500' : '#e04444') }}>{wsStatus}</span>
                    </div>
                    <input
                        aria-label="Control API key"
                        placeholder="API key"
                        value={key}
                        onChange={(e) => setKey(e.target.value)}
                        style={{ padding: '6px 8px', fontSize: 12, minWidth: 180 }}
                        className="vscode-input"
                    />
                    <button className="vscode-small-button" onClick={save} style={{ padding: '6px 10px' }}>Save</button>
                    <button className="vscode-small-button" onClick={clear} style={{ padding: '6px 10px' }}>Clear</button>
                </div>
            </div>
        </div>
    );
}
