import React, { useMemo } from "react";

const AVG_CHARS_PER_TOKEN = 4;
const DEFAULT_MAX_TOKENS = 32768;

/**
 * Slim 6-px token usage bar at the top of the input area.
 * @param {Array} messages - current message array
 * @param {number} maxTokens - context window size (from model settings)
 */
export default function TokenBar({ messages = [], maxTokens = DEFAULT_MAX_TOKENS }) {
  const { used, pct, colorClass, tooltip } = useMemo(() => {
    const chars = messages.reduce((sum, m) => sum + (m.text || "").length, 0);
    const used = Math.round(chars / AVG_CHARS_PER_TOKEN);
    const pct = Math.min(100, (used / maxTokens) * 100);
    const colorClass = pct > 90 ? "red" : pct > 70 ? "yellow" : "green";
    const tooltip = `${used.toLocaleString()} / ${maxTokens.toLocaleString()} tokens (est.)`;
    return { used, pct, colorClass, tooltip };
  }, [messages, maxTokens]);

  return (
    <div className="token-bar-wrapper" title={tooltip}>
      <div
        className={`token-bar-fill ${colorClass}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
