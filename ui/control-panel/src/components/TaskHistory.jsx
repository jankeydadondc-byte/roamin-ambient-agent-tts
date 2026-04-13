import React from "react";
import { getTaskHistory } from "../apiClient.js";

const STATUS_COLORS = {
    completed: "#4caf50",
    failed: "#f44336",
    running: "#2196f3",
    pending: "#ff9800",
};

function statusColor(s) {
    return STATUS_COLORS[s] || "#888";
}

function fmt(ts) {
    if (!ts) return "-";
    try {
        return new Date(ts).toLocaleString();
    } catch (e) {
        return ts;
    }
}

export default function TaskHistory({ tasks: propTasks = [] }) {
    // --- Server pagination state ---
    const [page, setPage] = React.useState(1);
    const [totalPages, setTotalPages] = React.useState(1);
    const [total, setTotal] = React.useState(0);
    const [rows, setRows] = React.useState(null); // null = not yet loaded
    const [loading, setLoading] = React.useState(false);

    // --- Filter state ---
    const [keyword, setKeyword] = React.useState("");
    const [status, setStatus] = React.useState("");
    const [taskType, setTaskType] = React.useState("");
    const [since, setSince] = React.useState("");

    // --- Expanded row ---
    const [expanded, setExpanded] = React.useState(null);

    // --- Fetch from server ---
    const fetchPage = React.useCallback(async (p) => {
        setLoading(true);
        try {
            const data = await getTaskHistory({
                page: p,
                perPage: 20,
                q: keyword || null,
                status: status || null,
                taskType: taskType || null,
                since: since || null,
            });
            setRows(data.tasks || []);
            setTotal(data.total ?? 0);
            setTotalPages(data.pages ?? 1);
            setPage(data.page ?? p);
        } catch (e) {
            // fallback to prop tasks
            setRows(propTasks);
            setTotal(propTasks.length);
            setTotalPages(1);
            setPage(1);
        } finally {
            setLoading(false);
        }
    }, [keyword, status, taskType, since, propTasks]);

    // Fetch on mount and when page changes
    React.useEffect(() => {
        fetchPage(page);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [page]);

    // Reset to page 1 and fetch when filters change
    const applyFilters = () => {
        setExpanded(null);
        if (page === 1) {
            fetchPage(1);
        } else {
            setPage(1); // triggers useEffect above
        }
    };

    const resetFilters = () => {
        setKeyword("");
        setStatus("");
        setTaskType("");
        setSince("");
        setExpanded(null);
        setPage(1);
    };

    // Re-fetch when reset clears state (side-effect on next render)
    const prevFilters = React.useRef({ keyword, status, taskType, since });
    React.useEffect(() => {
        const prev = prevFilters.current;
        if (
            prev.keyword !== keyword ||
            prev.status !== status ||
            prev.taskType !== taskType ||
            prev.since !== since
        ) {
            prevFilters.current = { keyword, status, taskType, since };
        }
    }, [keyword, status, taskType, since]);

    const displayRows = rows ?? propTasks;

    return (
        <div className="vscode-card" style={{ padding: 8 }}>
            {/* Filter bar */}
            <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
                <input
                    placeholder="Search tasks…"
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && applyFilters()}
                    className="vscode-input"
                    style={{ flex: "2 1 120px", minWidth: 80 }}
                />
                <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="vscode-input"
                    style={{ flex: "1 1 90px", minWidth: 80 }}
                >
                    <option value="">All statuses</option>
                    <option value="completed">completed</option>
                    <option value="failed">failed</option>
                    <option value="running">running</option>
                    <option value="pending">pending</option>
                </select>
                <input
                    placeholder="Task type"
                    value={taskType}
                    onChange={(e) => setTaskType(e.target.value)}
                    className="vscode-input"
                    style={{ flex: "1 1 90px", minWidth: 80 }}
                />
                <input
                    type="date"
                    value={since}
                    onChange={(e) => setSince(e.target.value)}
                    className="vscode-input"
                    title="Since date"
                    style={{ flex: "1 1 110px", minWidth: 100 }}
                />
                <button className="vscode-small-button" onClick={applyFilters} disabled={loading}>
                    Search
                </button>
                <button className="vscode-small-button" onClick={resetFilters} disabled={loading}>
                    Reset
                </button>
            </div>

            {/* Summary line */}
            <div style={{ fontSize: 12, color: "#888", marginBottom: 6 }}>
                {loading ? "Loading…" : `${total} task${total !== 1 ? "s" : ""} total`}
            </div>

            {/* Table */}
            {displayRows.length === 0 && !loading ? (
                <div style={{ color: "#888", padding: "12px 0" }}>No tasks found</div>
            ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead>
                        <tr style={{ textAlign: "left", color: "#666" }}>
                            <th style={{ padding: "4px 8px" }}>ID</th>
                            <th style={{ padding: "4px 8px" }}>Goal</th>
                            <th style={{ padding: "4px 8px" }}>Type</th>
                            <th style={{ padding: "4px 8px" }}>Status</th>
                            <th style={{ padding: "4px 8px" }}>Started</th>
                        </tr>
                    </thead>
                    <tbody>
                        {displayRows.map((t, idx) => {
                            const id = t.id ?? t.task_id ?? idx;
                            const isExpanded = expanded === id;
                            return (
                                <React.Fragment key={id}>
                                    <tr
                                        style={{
                                            borderTop: "1px solid #2a2a2a",
                                            cursor: "pointer",
                                            background: isExpanded ? "#1e2a1e" : "transparent",
                                        }}
                                        onClick={() => setExpanded(isExpanded ? null : id)}
                                    >
                                        <td style={{ fontFamily: "monospace", padding: "6px 8px", color: "#888" }}>
                                            {id}
                                        </td>
                                        <td style={{ padding: "6px 8px", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                            {t.goal || t.action || "-"}
                                        </td>
                                        <td style={{ padding: "6px 8px", color: "#aaa" }}>
                                            {t.task_type || t.type || "-"}
                                        </td>
                                        <td style={{ padding: "6px 8px" }}>
                                            <span style={{
                                                color: statusColor(t.status),
                                                fontWeight: 600,
                                                fontSize: 12,
                                            }}>
                                                {t.status || "-"}
                                            </span>
                                        </td>
                                        <td style={{ padding: "6px 8px", color: "#aaa", fontSize: 12 }}>
                                            {fmt(t.created_at || t.started_at || t.timestamp)}
                                        </td>
                                    </tr>
                                    {isExpanded && (
                                        <tr style={{ background: "#1a1a1a" }}>
                                            <td colSpan={5} style={{ padding: "8px 16px" }}>
                                                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: 12, color: "#ccc" }}>
                                                    <span style={{ color: "#888" }}>Goal</span>
                                                    <span>{t.goal || "-"}</span>
                                                    <span style={{ color: "#888" }}>Type</span>
                                                    <span>{t.task_type || "-"}</span>
                                                    <span style={{ color: "#888" }}>Steps</span>
                                                    <span>{t.step_count ?? "-"}</span>
                                                    <span style={{ color: "#888" }}>Started</span>
                                                    <span>{fmt(t.created_at || t.started_at)}</span>
                                                    <span style={{ color: "#888" }}>Finished</span>
                                                    <span>{fmt(t.finished_at)}</span>
                                                    {t.error && (
                                                        <>
                                                            <span style={{ color: "#f44" }}>Error</span>
                                                            <span style={{ color: "#f44" }}>{t.error}</span>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </React.Fragment>
                            );
                        })}
                    </tbody>
                </table>
            )}

            {/* Pagination controls */}
            {totalPages > 1 && (
                <div style={{ display: "flex", gap: 6, justifyContent: "center", alignItems: "center", marginTop: 10 }}>
                    <button
                        className="vscode-small-button"
                        onClick={() => setPage(1)}
                        disabled={page <= 1 || loading}
                        title="First page"
                    >«</button>
                    <button
                        className="vscode-small-button"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1 || loading}
                        title="Previous page"
                    >‹</button>
                    <span style={{ fontSize: 12, color: "#aaa", minWidth: 60, textAlign: "center" }}>
                        {page} / {totalPages}
                    </span>
                    <button
                        className="vscode-small-button"
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages || loading}
                        title="Next page"
                    >›</button>
                    <button
                        className="vscode-small-button"
                        onClick={() => setPage(totalPages)}
                        disabled={page >= totalPages || loading}
                        title="Last page"
                    >»</button>
                </div>
            )}
        </div>
    );
}
