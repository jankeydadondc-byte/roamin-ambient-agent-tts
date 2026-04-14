import React from "react";

/**
 * Collapsible reasoning block shown above an assistant response.
 * Collapsed by default — user clicks to expand.
 */
export default function ThinkingBlock({ reasoning }) {
  if (!reasoning) return null;
  return (
    <details className="thinking-block">
      <summary>▶ Reasoning</summary>
      <div className="thinking-content">{reasoning}</div>
    </details>
  );
}
