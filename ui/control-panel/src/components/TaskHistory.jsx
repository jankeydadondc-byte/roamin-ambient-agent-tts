import React from "react";

export default function TaskHistory({ tasks = [] }) {
    const [filter, setFilter] = React.useState('');
    const [showCount, setShowCount] = React.useState(5);

    const filtered = (tasks || []).filter((t) => {
        if (!filter) return true;
        try {
            return JSON.stringify(t).toLowerCase().includes(filter.toLowerCase());
        } catch (e) { return false; }
    });

    if (!filtered.length) return (
        <div className="vscode-card" style={{ padding: 12 }}>
            <div style={{ color: '#888' }}>No tasks yet</div>
        </div>
    );

    return (
        <div className="vscode-card" style={{ padding: 8 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                <input placeholder="Filter tasks" value={filter} onChange={(e) => setFilter(e.target.value)} className="vscode-input" style={{ flex: 1 }} />
                <button className="vscode-small-button" onClick={() => { setFilter(''); setShowCount(5); }}>Reset</button>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                    <tr style={{ textAlign: 'left', color: '#666' }}>
                        <th>ID</th>
                        <th>Plugin</th>
                        <th>Action</th>
                        <th>Status</th>
                        <th>Started</th>
                    </tr>
                </thead>
                <tbody>
                    {filtered.slice(0, showCount).map((t, idx) => (
                        <tr key={t.task_id || t.id || idx} style={{ borderTop: '1px solid #eee' }}>
                            <td style={{ fontFamily: 'monospace', padding: '6px 8px' }}>{t.task_id || t.id || '-'}</td>
                            <td style={{ padding: '6px 8px' }}>{t.plugin || t.plugin_id || '-'}</td>
                            <td style={{ padding: '6px 8px' }}>{t.type || t.action || '-'}</td>
                            <td style={{ padding: '6px 8px' }}>{t.status || '-'}</td>
                            <td style={{ padding: '6px 8px' }}>{t.timestamp || t.created_at || '-'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {filtered.length > showCount && (
                <div style={{ marginTop: 8, textAlign: 'center' }}>
                    <button className="vscode-small-button" onClick={() => setShowCount((c) => c + 10)}>Show more</button>
                </div>
            )}
        </div>
    );
}
