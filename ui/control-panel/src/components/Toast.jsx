import { createContext, useCallback, useContext, useEffect, useState } from "react";

// =============================================
// Toast Context
// =============================================
const ToastContext = createContext(null);

// =============================================
// ToastProvider — wrap the app with this
// =============================================
export default function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = "info") => {
        const id = Date.now() + Math.random();
        setToasts((prev) => [...prev, { id, message, type }]);
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 5000);
    }, []);

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const showToast = {
        info: (msg) => addToast(msg, "info"),
        success: (msg) => addToast(msg, "success"),
        error: (msg) => addToast(msg, "error"),
        warning: (msg) => addToast(msg, "warning"),
    };

    return (
        <ToastContext.Provider value={{ showToast }}>
            {children}
            <div
                style={{
                    position: "fixed",
                    top: 20,
                    right: 20,
                    zIndex: 9999,
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    pointerEvents: "none",
                }}
                aria-live="polite"
                aria-atomic="false"
            >
                {toasts.map((toast) => (
                    <ToastItem
                        key={toast.id}
                        {...toast}
                        onDismiss={() => removeToast(toast.id)}
                    />
                ))}
            </div>
        </ToastContext.Provider>
    );
}

// =============================================
// useToast hook — use inside ToastProvider
// =============================================
export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
    return ctx;
}

// =============================================
// ToastItem — private UI component
// =============================================
function ToastItem({ message, type = "info", onDismiss }) {
    const [visible, setVisible] = useState(true);

    useEffect(() => {
        const esc = (e) => {
            if (e.key === "Escape") {
                setVisible(false);
                onDismiss?.();
            }
        };
        document.addEventListener("keydown", esc);
        return () => document.removeEventListener("keydown", esc);
    }, [onDismiss]);

    if (!visible) return null;

    const COLORS = {
        success: { background: "#1b4332", border: "#2f6f45", icon: "✓", text: "#e0eee8" },
        error:   { background: "#5c2222", border: "#a63838", icon: "✗", text: "#f5d0d0" },
        warning: { background: "#3e2f14", border: "#7c5a24", icon: "⚠", text: "#eee8cc" },
        info:    { background: "#003d6d", border: "#1e7bc9", icon: "ℹ", text: "#cce4f7" },
    };
    const c = COLORS[type] ?? COLORS.info;

    return (
        <div
            role="alert"
            aria-live="assertive"
            style={{
                pointerEvents: "all",
                background: c.background,
                border: `3px solid ${c.border}`,
                borderRadius: 8,
                boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
                padding: "16px 20px",
                maxWidth: 450,
                minWidth: 300,
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                animation: "toast-slide-in 0.25s ease",
            }}
        >
            <span style={{ fontSize: 20, flexShrink: 0, lineHeight: 1 }}>{c.icon}</span>
            <span style={{ flex: 1, color: c.text, fontSize: 14, lineHeight: 1.5 }}>{message}</span>
            <button
                onClick={() => { setVisible(false); onDismiss?.(); }}
                aria-label="Dismiss notification"
                style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: "4px 8px",
                    fontSize: 20,
                    lineHeight: 1,
                    opacity: 0.7,
                    color: c.text,
                }}
            >
                &times;
            </button>
            <style>{`
                @keyframes toast-slide-in {
                    from { transform: translateX(100%); opacity: 0; }
                    to   { transform: translateX(0);    opacity: 1; }
                }
            `}</style>
        </div>
    );
}
