
export default function PluginList({ plugins, onSelect, onRefresh, value }) {
    const handleChange = (e) => {
        const id = e.target.value;
        const p = plugins.find((pl) => pl.id === id) || null;
        onSelect && onSelect(p);
    };

    return (
        <div>
            <label htmlFor="plugin-select" style={{ display: 'block', marginBottom: 6 }}>Plugins</label>
            <select id="plugin-select" className="vscode-input" value={value ? value.id : ""} onChange={handleChange} style={{ minWidth: 240 }} aria-label="Select plugin">
                <option value="">Select plugin...</option>
                {plugins.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} — {p.enabled ? "enabled" : "disabled"}</option>
                ))}
            </select>
            <button className="vscode-small-button" onClick={() => onRefresh && onRefresh()} style={{ marginLeft: 8 }}>Refresh</button>
        </div>
    );
}
