import React, { useState, useEffect, useRef, useCallback } from "react";
import { sendMessage, getChatHistory, resetChat, getPendingNotifications } from "../apiClient";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingNotifications, setPendingNotifications] = useState([]);
  const chatEndRef = useRef(null);

  // Load history on mount
  useEffect(() => {
    getChatHistory()
      .then((data) => {
        if (data.exchanges && data.exchanges.length > 0) {
          const parsed = data.exchanges.map((ex) => {
            // Parse "User: ..." or "Roamin: ..." from content field
            const content = ex.content || "";
            const isUser = content.startsWith("User:");
            return {
              role: isUser ? "user" : "assistant",
              text: content.replace(/^(User|Roamin):\s*/, ""),
              timestamp: ex.timestamp,
            };
          });
          setMessages(parsed);
        }
      })
      .catch(() => {});

    // Check for pending proactive notifications
    getPendingNotifications()
      .then((data) => {
        if (data.messages && data.messages.length > 0) {
          setPendingNotifications(data.messages);
        }
      })
      .catch(() => {});
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    // Add user message immediately
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);

    try {
      const result = await sendMessage(text);
      console.log("[Chat] sendMessage result:", result);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.response || "Done." },
      ]);
    } catch (err) {
      console.error("[Chat] sendMessage failed:", err);
      const errorMsg = err.message || "Sorry, something went wrong.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${errorMsg}` },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleReset = async () => {
    try {
      await resetChat();
      setMessages([]);
    } catch (err) {
      console.error("Reset failed:", err);
    }
  };

  return (
    <>
      <div className="chat-area">
        {/* Pending notifications from proactive engine */}
        {pendingNotifications.length > 0 && (
          <div className="pending-banner">
            <strong>Roamin wanted to say:</strong>
            {pendingNotifications.map((n, i) => (
              <div key={i} style={{ marginTop: 4 }}>
                {n.message || n}
              </div>
            ))}
            <button
              style={{
                marginTop: 6,
                fontSize: 11,
                padding: "2px 8px",
                cursor: "pointer",
              }}
              onClick={() => setPendingNotifications([])}
            >
              Dismiss
            </button>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="role">{msg.role === "user" ? "You" : "Roamin"}</div>
            <div className="text">{msg.text}</div>
          </div>
        ))}

        {sending && (
          <div className="message assistant">
            <div className="role">Roamin</div>
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div className="input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          disabled={sending}
          autoFocus
        />
        <button onClick={handleSend} disabled={sending || !input.trim()}>
          Send
        </button>
      </div>
    </>
  );
}
