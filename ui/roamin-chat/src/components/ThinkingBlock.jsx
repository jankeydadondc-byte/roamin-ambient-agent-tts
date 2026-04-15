import React, { useState, useRef, useEffect } from "react";

/**
 * Claude-style collapsible reasoning block shown above an assistant response.
 * Collapsed by default — shows "Thought for X seconds" with a sparkle icon.
 * Click the header bar to expand/collapse with smooth animation.
 *
 * @param {string|null} reasoning    - the raw thinking text
 * @param {number|null} thinkSeconds - how long the model spent thinking
 */
export default function ThinkingBlock({ reasoning, thinkSeconds }) {
  if (!reasoning) return null;

  const [expanded, setExpanded] = useState(false);
  const contentRef = useRef(null);
  const [contentHeight, setContentHeight] = useState(0);

  // Measure actual content height for smooth animation
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [reasoning, expanded]);

  const timeLabel = thinkSeconds
    ? `Thought for ${thinkSeconds}s`
    : "Reasoning";

  return (
    <div className={`thinking-block-v2 ${expanded ? "expanded" : ""}`}>
      <div
        className="thinking-header"
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setExpanded(!expanded); }}
      >
        <span className="thinking-icon">&#10023;</span>
        <span className="thinking-label">{timeLabel}</span>
        <span className={`thinking-chevron ${expanded ? "open" : ""}`}>&#9656;</span>
      </div>
      <div
        className="thinking-content-wrapper"
        style={{ maxHeight: expanded ? Math.min(contentHeight, 400) : 0 }}
      >
        <div className="thinking-content-v2" ref={contentRef}>
          {reasoning}
        </div>
      </div>
    </div>
  );
}
