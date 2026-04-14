/**
 * exportChat — formats the messages array as Markdown and triggers a file download.
 * @param {Array<{role: string, text: string, timestamp?: string}>} messages
 */
export function exportChat(messages) {
  if (!messages || messages.length === 0) return;

  const dateStr = new Date().toISOString().split("T")[0];
  const lines = [`# Roamin Chat — ${dateStr}`, ""];

  for (const msg of messages) {
    const speaker = msg.role === "user" ? "**You**" : "**Roamin**";
    const ts = msg.timestamp
      ? ` *(${new Date(msg.timestamp).toLocaleTimeString()})*`
      : "";
    lines.push(`### ${speaker}${ts}`);
    lines.push(msg.text || "");
    lines.push("");
  }

  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `roamin-chat-${dateStr}.md`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
