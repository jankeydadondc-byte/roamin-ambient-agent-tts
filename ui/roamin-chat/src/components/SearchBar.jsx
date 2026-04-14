import React, { useRef, useEffect } from "react";

/**
 * In-chat search bar that slides down from the header.
 * @param {string}   query       - current search query (controlled)
 * @param {Function} onChange    - called with new query string
 * @param {number}   matchCount  - total number of matches found in messages
 * @param {number}   matchIndex  - currently highlighted match (0-based)
 * @param {Function} onPrev      - navigate to previous match
 * @param {Function} onNext      - navigate to next match
 * @param {Function} onClose     - close the search bar
 */
export default function SearchBar({
  query,
  onChange,
  matchCount = 0,
  matchIndex = 0,
  onPrev,
  onNext,
  onClose,
}) {
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKey = (e) => {
    if (e.key === "Escape") onClose();
    if (e.key === "Enter") e.shiftKey ? onPrev() : onNext();
  };

  const countLabel =
    query && matchCount > 0
      ? `${matchIndex + 1} / ${matchCount}`
      : query
      ? "0 results"
      : "";

  return (
    <div className="search-bar">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Search in chat…"
      />
      <span className="search-bar-count">{countLabel}</span>
      <button className="search-nav-btn" onClick={onPrev} title="Previous (Shift+Enter)" disabled={matchCount === 0}>
        ▲
      </button>
      <button className="search-nav-btn" onClick={onNext} title="Next (Enter)" disabled={matchCount === 0}>
        ▼
      </button>
      <button className="search-close-btn" onClick={onClose} title="Close search (Esc)">
        ✕
      </button>
    </div>
  );
}
