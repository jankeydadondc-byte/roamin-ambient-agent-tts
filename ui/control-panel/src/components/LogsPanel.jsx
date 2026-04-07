import { useEffect, useRef, useState } from "react";
import { useToast } from "./Toast";

export default function LogsPanel() {
    const { showToast } = useToast();
    const [logs, setLogs] = useState([
        { id: 1, timestamp: new Date().toISOString(), level: "info", message: "Roamin agent initialized" },
        { id: 2, timestamp: new Date().toISOString(), level: "success", message: "TTS model 'piper' loaded successfully" },
        { id: 3, timestamp: new Date().toISOString(), level: "warning", message: "High memory usage detected (75%)" },
    ]);
    const [newLog, setNewLog] = useState("");
    const [isAutoScrolling, setIsAutoScrolling] = useState(true);
    const logsEndRef = useRef(null);

    useEffect(() => {
        if (isAutoScrolling && logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [logs, isAutoScrolling]);

    // Simulate real-time log updates
    useEffect(() => {
        const messages = [
            "Processing audio request",
            "Memory optimization cycle completed",
            "Model inference time: 0.45s",
            "Audio buffer refreshed",
        ];
        const levels = ["info", "success", "warning", "error"];
        const interval = setInterval(() => {
            if (Math.random() > 0.7) {
                setLogs((prev) => [
                    ...prev,
                    {
                        id: Date.now(),
                        timestamp: new Date().toISOString(),
                        level: levels[Math.floor(Math.random() * levels.length)],
                        message: messages[Math.floor(Math.random() * messages.length)],
                    },
                ]);
            }
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    const handleAddLog = (e) => {
        e.preventDefault();
        if (!newLog.trim()) {
            showToast.warning("Please enter a log message");
            return;
        }
        setLogs((prev) => [
            ...prev,
            { id: Date.now(), timestamp: new Date().toISOString(), level: "info", message: newLog },
        ]);
        setNewLog("");
        showToast.success("Log entry added successfully");
    };

    const clearLogs = () => {
        if (logs.length > 0) {
            setLogs([]);
            showToast.info("All logs cleared");
        } else {
            showToast.warning("No logs to clear");
        }
    };

    const getLevelColor = (level) => {
        switch (level) {
            case "error":   return { bg: "#5c2222", text: "#f5d0d0" };
            case "warning": return { bg: "#3e2f14", text: "#eee8cc" };
            case "success": return { bg: "#1b4332", text: "#e0eee8" };
            default:        return { bg: "#003d6d", text: "#cce4f7" };
        }
    };

    const formatTime = (ts) => {
        const d = new Date(ts);
        return d.toLocaleTimeString() + "." + d.getMilliseconds().toString().padStart(3, "0");
    };

    return (
        <section className="logs-panel" aria-labelledby="logs-heading">
            <div className="panel-header">
                <h2 id="logs-heading">System Logs</h2>
                <div className="log-controls">
                    <button
                        type="button"
                        onClick={() => setIsAutoScrolling((v) => !v)}
                        className={`btn-secondary ${isAutoScrolling ? "active" : ""}`}
                        aria-pressed={isAutoScrolling}
                        aria-label={isAutoScrolling ? "Disable auto-scrolling" : "Enable auto-scrolling"}
                    >
                        {isAutoScrolling ? "Auto-scroll: ON" : "Auto-scroll: OFF"}
                    </button>
                    <button
                        type="button"
                        onClick={clearLogs}
                        className="btn-secondary"
                        aria-label="Clear all logs"
                        disabled={logs.length === 0}
                    >
                        Clear Logs
                    </button>
                </div>
            </div>

            <form onSubmit={handleAddLog} className="log-entry-form">
                <div className="form-group">
                    <label htmlFor="new-log" className="sr-only">
                        New log message
                    </label>
                    <input
                        type="text"
                        id="new-log"
                        value={newLog}
                        onChange={(e) => setNewLog(e.target.value)}
                        placeholder="Type a new log entry..."
                        aria-describedby="log-input-hint"
                        className="form-control"
                    />
                    <div id="log-input-hint" className="hint-text">
                        Add custom log entries or use the auto-generated logs below
                    </div>
                </div>
                <button type="submit" className="btn-primary" disabled={!newLog.trim()}>
                    Add Log Entry
                </button>
            </form>

            <div
                className="logs-container"
                role="log"
                aria-live="polite"
                aria-relevant="additions"
                style={{ maxHeight: 400, overflowY: "auto" }}
            >
                {logs.length === 0 ? (
                    <div className="empty-state" role="status" aria-live="polite">
                        <p>No logs available yet</p>
                        <button
                            type="button"
                            onClick={() => showToast.info("Waiting for system events...")}
                        >
                            Refresh
                        </button>
                    </div>
                ) : (
                    <ul className="logs-list" role="list">
                        {logs.map((log) => {
                            const colors = getLevelColor(log.level);
                            return (
                                <li
                                    key={log.id}
                                    role="listitem"
                                    className={`log-entry log-${log.level}`}
                                    style={{
                                        borderLeft: `4px solid var(--${log.level === "error" ? "error-color" : log.level === "warning" ? "warning-color" : log.level === "success" ? "success-color" : "accent-color"})`,
                                    }}
                                >
                                    <div className="log-header">
                                        <time dateTime={log.timestamp} className="log-time">
                                            {formatTime(log.timestamp)}
                                        </time>
                                        <span
                                            className={`log-level badge ${log.level}`}
                                            style={{ backgroundColor: colors.bg, color: colors.text }}
                                        >
                                            {log.level.toUpperCase()}
                                        </span>
                                    </div>
                                    <p className="log-message">{log.message}</p>
                                </li>
                            );
                        })}
                        <li ref={logsEndRef} style={{ height: 0 }} />
                    </ul>
                )}
            </div>

            {logs.length > 0 && (
                <div className="log-summary">
                    <p>
                        Showing <strong>{logs.length}</strong> log entries
                    </p>
                    <div className="legend">
                        <span className="legend-item error">
                            <span />
                            Error
                        </span>
                        <span className="legend-item warning">
                            <span />
                            Warning
                        </span>
                        <span className="legend-item success">
                            <span />
                            Success
                        </span>
                        <span className="legend-item info">
                            <span />
                            Info
                        </span>
                    </div>
                </div>
            )}
        </section>
    );
}
