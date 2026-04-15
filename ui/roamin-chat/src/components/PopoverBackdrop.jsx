import { useEffect } from "react";
import { createPortal } from "react-dom";

/**
 * Invisible full-viewport backdrop rendered at the document body level.
 * Sits between popovers (z-index 999) and everything else (z-index < 999).
 * Any mousedown that lands on the backdrop unconditionally closes the popover.
 *
 * This is the industry-standard approach (Radix UI, Headless UI, etc.) and
 * avoids all edge cases with DOM contains-checks and WebView2 event bubbling.
 */
export default function PopoverBackdrop({ onClose }) {
  // Also close on Escape key
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 998,
        background: "transparent",
      }}
      onMouseDown={(e) => {
        e.preventDefault();
        onClose();
      }}
    />,
    document.body
  );
}
