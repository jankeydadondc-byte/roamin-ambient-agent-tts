import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Ensure React is available globally for any modules relying on the classic runtime
if (typeof window !== "undefined") window.React = React;

createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);
