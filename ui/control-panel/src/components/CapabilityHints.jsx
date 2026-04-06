
const HINTS = {
    filesystem: 'Allows read/write access to the filesystem under the plugin directory.',
    network: 'Allows outbound network access (HTTP, sockets). Use with caution for untrusted plugins.',
    microphone: 'Access to microphone audio input.',
    camera: 'Access to camera/video input.',
};

export default function CapabilityHints({ capabilities = [] }) {
    if (!capabilities || capabilities.length === 0) return <div style={{ color: '#888' }}>No special capabilities requested.</div>;
    return (
        <ul style={{ marginTop: 6 }}>
            {capabilities.map((c) => (
                <li key={c}>
                    <strong>{c}</strong>: {HINTS[c] || 'Required capability — review before granting.'}
                </li>
            ))}
        </ul>
    );
}
