import React, { useState } from "react";

/**
 * Displays the live planning / tool-execution / reflect status
 * above the assistant's streaming reply.
 *
 * Props:
 *   planning    {bool}   — currently in PLAN phase
 *   planSeconds {number|null}
 *   planSteps   {number|null}
 *   toolSteps   {Array}  — [{tool, step, action, status:"running"|"ok"|"error", seconds, error}]
 *   reflecting  {bool}   — currently in REFLECT phase
 *   reflectCycles {Array} — [{cycle, verdict, tool, seconds}]
 */
export default function ToolStatus({ planning, planSeconds, planSteps, toolSteps, reflecting, reflectCycles }) {
  const [expanded, setExpanded] = useState(true);

  const hasActivity = planning || (toolSteps && toolSteps.length > 0) || reflecting || (reflectCycles && reflectCycles.length > 0);
  if (!hasActivity) return null;

  const allDone = !planning && !reflecting && toolSteps?.every((s) => s.status !== "running");
  const totalSteps = toolSteps?.length || 0;
  const doneSteps = toolSteps?.filter((s) => s.status === "ok").length || 0;

  let headerLabel;
  if (planning) {
    headerLabel = "Planning…";
  } else if (reflecting) {
    headerLabel = "Reflecting…";
  } else if (!allDone && totalSteps > 0) {
    headerLabel = `Running tools (${doneSteps}/${totalSteps})`;
  } else if (allDone && totalSteps > 0) {
    const secs = planSeconds ? ` · ${planSeconds}s` : "";
    headerLabel = `Used ${totalSteps} tool${totalSteps !== 1 ? "s" : ""}${secs}`;
  } else {
    headerLabel = "Working…";
  }

  return (
    <div className={`tool-status ${allDone ? "done" : "active"}`}>
      <div
        className="tool-status-header"
        onClick={() => setExpanded((x) => !x)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setExpanded((x) => !x); }}
      >
        <span className={`tool-status-icon ${planning || reflecting || !allDone ? "spinning" : ""}`}>
          {planning ? "🗺" : reflecting ? "🔄" : allDone ? "✓" : "⚙"}
        </span>
        <span className="tool-status-label">{headerLabel}</span>
        <span className={`tool-status-chevron ${expanded ? "open" : ""}`}>▶</span>
      </div>

      {expanded && (
        <div className="tool-status-body">
          {/* Planning row */}
          {(planning || planSeconds != null) && (
            <div className={`ts-row ${planning ? "running" : "ok"}`}>
              <span className="ts-icon">{planning ? "⟳" : "✓"}</span>
              <span className="ts-name">Plan</span>
              {planSteps != null && <span className="ts-detail">{planSteps} step{planSteps !== 1 ? "s" : ""}</span>}
              {planSeconds != null && <span className="ts-time">{planSeconds}s</span>}
            </div>
          )}

          {/* Tool execution rows */}
          {(toolSteps || []).map((s) => (
            <div key={`${s.tool}-${s.step}`} className={`ts-row ${s.status}`}>
              <span className="ts-icon">
                {s.status === "running" ? "⟳" : s.status === "ok" ? "✓" : "✗"}
              </span>
              <span className="ts-name" title={s.action}>{s.tool}</span>
              {s.status === "ok" && s.seconds != null && <span className="ts-time">{s.seconds}s</span>}
              {s.status === "error" && <span className="ts-error" title={s.error}>failed</span>}
            </div>
          ))}

          {/* Reflect rows */}
          {(reflectCycles || []).map((c) => (
            <div key={`reflect-${c.cycle}`} className={`ts-row ${c.verdict === "ready" ? "ok" : "running"}`}>
              <span className="ts-icon">{c.verdict === "ready" ? "✓" : "⟳"}</span>
              <span className="ts-name">Reflect #{c.cycle}</span>
              {c.verdict && <span className="ts-detail">{c.verdict === "ready" ? "ready" : `→ ${c.tool}`}</span>}
              {c.seconds != null && <span className="ts-time">{c.seconds}s</span>}
            </div>
          ))}

          {reflecting && (
            <div className="ts-row running">
              <span className="ts-icon">⟳</span>
              <span className="ts-name">Reflecting…</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
