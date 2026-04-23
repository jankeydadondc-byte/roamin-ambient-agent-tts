import React from "react";

export default function Help() {
    const voiceCommands = [
        { phrase: "ctrl+space", action: "Wake up Roamin, listen for speech" },
        { phrase: "What time is it?", action: "Direct dispatch → clock tool" },
        { phrase: "Search for X", action: "Direct dispatch → web search" },
        { phrase: "Search my memories for X", action: "Direct dispatch → mempalace search" },
        { phrase: "Anything else", action: "Full AgentLoop reasoning" },
    ];

    const tabDescriptions = [
        { tab: "Models", desc: "Select which LLM to use for next task execution" },
        { tab: "Plugins", desc: "View installed plugins, enable/disable them" },
        { tab: "Tasks", desc: "Task execution history with step-by-step details" },
        { tab: "Logs", desc: "Live WebSocket event stream (planning, execution)" },
        { tab: "Supervisor", desc: "Real-time monitoring of agent state" },
    ];

    const shortcuts = [
        { key: "ctrl+space", desc: "Wake and listen for voice command" },
        { key: "Escape", desc: "Dismiss active toast notification" },
        { key: "↓ / ↑", desc: "Navigate sidebar items (when focused)" },
        { key: "Enter", desc: "Activate selected sidebar item" },
    ];

    return (
        <div className="vscode-card" style={{ padding: 12 }}>
            <div style={{ fontSize: 13, lineHeight: 1.6, color: "#ccc" }}>
                {/* Voice Commands Section */}
                <div style={{ marginBottom: 16 }}>
                    <h4 style={{ margin: "0 0 8px 0", color: "#fff" }}>Voice Commands</h4>
                    <p style={{ margin: "0 0 8px 0", fontSize: 12, color: "#888" }}>
                        Press <code style={{ background: "#1e1e1e", padding: "2px 4px" }}>ctrl+space</code> and say:
                    </p>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                        {voiceCommands.map((cmd, i) => (
                            <li key={i} style={{ marginBottom: 6 }}>
                                <strong>{cmd.phrase}</strong>
                                <br />
                                <span style={{ color: "#999" }}>→ {cmd.action}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                {/* Control Panel Tabs */}
                <div style={{ marginBottom: 16 }}>
                    <h4 style={{ margin: "0 0 8px 0", color: "#fff" }}>Control Panel Tabs</h4>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                        {tabDescriptions.map((t, i) => (
                            <li key={i} style={{ marginBottom: 4 }}>
                                <strong>{t.tab}</strong>
                                <span style={{ color: "#999" }}> — {t.desc}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                {/* Keyboard Shortcuts */}
                <div style={{ marginBottom: 16 }}>
                    <h4 style={{ margin: "0 0 8px 0", color: "#fff" }}>Keyboard Shortcuts</h4>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <tbody>
                            {shortcuts.map((s, i) => (
                                <tr key={i}>
                                    <td style={{ padding: "4px 8px 4px 0", borderBottom: "1px solid #2a2a2a" }}>
                                        <code style={{ background: "#1e1e1e", padding: "2px 4px" }}>
                                            {s.key}
                                        </code>
                                    </td>
                                    <td style={{ padding: "4px 0", borderBottom: "1px solid #2a2a2a", color: "#999" }}>
                                        {s.desc}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Quick Links */}
                <div style={{ marginBottom: 16 }}>
                    <h4 style={{ margin: "0 0 8px 0", color: "#fff" }}>Documentation</h4>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                        <li style={{ marginBottom: 6 }}>
                            <a href="https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts#quick-start"
                               target="_blank" rel="noopener noreferrer" style={{ color: "#569cd6" }}>
                                Quick Start Guide
                            </a>
                        </li>
                        <li style={{ marginBottom: 6 }}>
                            <a href="https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts/blob/main/docs/SETUP.md"
                               target="_blank" rel="noopener noreferrer" style={{ color: "#569cd6" }}>
                                Full Setup Instructions
                            </a>
                        </li>
                        <li style={{ marginBottom: 6 }}>
                            <a href="https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts/blob/main/docs/PLUGIN_DEVELOPMENT.md"
                               target="_blank" rel="noopener noreferrer" style={{ color: "#569cd6" }}>
                                Write Your Own Plugins
                            </a>
                        </li>
                        <li>
                            <a href="https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts/blob/main/docs/TROUBLESHOOTING.md"
                               target="_blank" rel="noopener noreferrer" style={{ color: "#569cd6" }}>
                                Troubleshooting Guide
                            </a>
                        </li>
                    </ul>
                </div>

                {/* Version Info */}
                <div style={{ paddingTop: 12, borderTop: "1px solid #2a2a2a" }}>
                    <p style={{ margin: 0, fontSize: 12, color: "#666" }}>
                        Roamin Ambient Agent<br />
                        <span style={{ fontSize: 11 }}>Priority 10 Documentation & Onboarding (2026-04-10)</span>
                    </p>
                </div>
            </div>
        </div>
    );
}
