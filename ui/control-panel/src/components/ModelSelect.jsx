
export default function ModelSelect({ models, value, onSelect }) {
    const handleChange = (e) => {
        const id = e.target.value;
        const m = models.find((mm) => mm.id === id) || null;
        onSelect && onSelect(m);
    };

    return (
        <div>
            <label htmlFor="model-select" style={{ display: 'block', marginBottom: 6 }} className="vscode-panel">Model</label>
            <select id="model-select" className="vscode-input" value={value ? value.id : ""} onChange={handleChange} style={{ minWidth: 240 }} aria-label="Select model">
                <option value="">Select model...</option>
                {models.map((m) => (
                    <option key={m.id} value={m.id}>{m.name} — {m.status}</option>
                ))}
            </select>
        </div>
    );
}
