import React, { useState, useRef, useEffect } from "react";

/**
 * Claude-style collapsible reasoning block.
 *
 * Modes:
 *  - streaming=true  → expanded with live content, pulsing header "Thinking…"
 *  - streaming=false → collapsed by default showing "Thought for Xs", click to expand
 */
export default function ThinkingBlock({ reasoning, thinkSeconds, streaming = false }) {
  if (!reasoning && !streaming) return null;

  const [expanded, setExpanded] = useState(streaming); // auto-expand while streaming
  const contentRef  = useRef(null);
  const [contentHeight, setContentHeight] = useState(0);

  // Auto-collapse when streaming completes
  useEffect(() => {
    if (!streaming && expanded) {
      // brief delay so user sees the final content before collapsing
      const t = setTimeout(() => setExpanded(false), 600);
      return () => clearTimeout(t);
    }
  }, [streaming]); // eslint-disable-line

  // Remeasure height whenever content changes
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [reasoning, expanded]);

  // Auto-scroll content during streaming
  useEffect(() => {
    if (streaming && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [reasoning, streaming]);

  const timeLabel = streaming
    ? "Thinking…"
    : thinkSeconds
      ? `Thought for ${thinkSeconds}s`
      : "Reasoning";

  return (
    <div className={`thinking-block-v2 ${expanded ? "expanded" : ""} ${streaming ? "streaming" : ""}`}>
      <div
        className="thinking-header"
        onClick={() => !streaming && setExpanded((x) => !x)}
        role="button"
        tabIndex={0}
        style={{ cursor: streaming ? "default" : "pointer" }}
        onKeyDown={(e) => {
          if (!streaming && (e.key === "Enter" || e.key === " ")) setExpanded((x) => !x);
        }}
      >
        <span className="thinking-icon" style={{ animation: streaming ? "thinking-pulse 1.2s ease-in-out infinite" : "none" }}>
          ✧
        </span>
        <span className="thinking-label">{timeLabel}</span>
        {!streaming && (
          <span className={`thinking-chevron ${expanded ? "open" : ""}`}>▶</span>
        )}
      </div>
      <div
        className="thinking-content-wrapper"
        style={{
          maxHeight: expanded ? (streaming ? 300 : Math.min(contentHeight + 20, 400)) : 0,
          overflow: streaming ? "auto" : "hidden",
        }}
      >
        <div className="thinking-content-v2" ref={contentRef}>
          {reasoning}
          {streaming && <span className="thinking-cursor">▋</span>}
        </div>
      </div>
    </div>
  );
}
