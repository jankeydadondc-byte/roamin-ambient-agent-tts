/**
 * Example JavaScript client for Roamin Control API
 *
 * Usage:
 *   node example_client.js
 *   // or in browser:
 *   // <script src="example_client.js"></script>
 *   // const client = new RoaminControlClient();
 *   // await client.getStatus().then(s => console.log(s));
 */

class RoaminControlClient {
  constructor(baseUrl = "http://127.0.0.1:8765") {
    this.baseUrl = baseUrl;
    this.apiKey = process.env?.ROAMIN_CONTROL_API_KEY || "";
  }

  /**
   * Helper to make authenticated requests
   */
  async request(method, path, body = null) {
    const options = {
      method,
      headers: {
        "Content-Type": "application/json",
      },
    };

    if (this.apiKey) {
      options.headers["x-roamin-api-key"] = this.apiKey;
    }

    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${path}`, options);
    if (!response.ok) {
      throw new Error(`${method} ${path} returned ${response.status}`);
    }
    return await response.json();
  }

  /**
   * Get system status
   */
  async getStatus() {
    return this.request("GET", "/status");
  }

  /**
   * List available models
   */
  async listModels() {
    return this.request("GET", "/models");
  }

  /**
   * List installed plugins
   */
  async listPlugins() {
    return this.request("GET", "/plugins");
  }

  /**
   * Install a plugin from file or URL
   * @param {string} source - "file" or "url"
   * @param {string} value - path or HTTPS URL
   */
  async installPlugin(source, value) {
    return this.request("POST", "/plugins/install", { source, value });
  }

  /**
   * Uninstall a plugin
   * @param {string} pluginId - Plugin identifier
   */
  async uninstallPlugin(pluginId) {
    return this.request("DELETE", `/plugins/${pluginId}`);
  }

  /**
   * Perform plugin action (enable, disable, restart)
   * @param {string} pluginId - Plugin identifier
   * @param {string} action - "enable", "disable", or "restart"
   */
  async pluginAction(pluginId, action) {
    return this.request("POST", `/plugins/${pluginId}/action`, { action });
  }

  /**
   * Get task history
   * @param {number} limit - Max tasks to return
   * @param {string} status - Filter by status (optional)
   */
  async getTaskHistory(limit = 100, status = null) {
    let path = `/task-history?limit=${limit}`;
    if (status) {
      path += `&status=${status}`;
    }
    return this.request("GET", path);
  }

  /**
   * Connect to WebSocket event stream
   * @param {function} onEvent - Callback for each event
   * @param {function} onError - Callback for errors
   */
  listenEvents(onEvent, onError) {
    const wsUrl = "ws://127.0.0.1:8765/ws/events";
    console.log(`[*] Connecting to ${wsUrl}`);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[+] Connected! Listening for events...");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log(`[EVENT] ${data.type}:`, data.data);
        if (onEvent) onEvent(data);
      } catch (err) {
        console.error("[!] Failed to parse event:", err);
      }
    };

    ws.onerror = (event) => {
      console.error("[!] WebSocket error:", event);
      if (onError) onError(event);
    };

    ws.onclose = () => {
      console.log("[-] Disconnected");
    };

    return ws;
  }
}

/**
 * Demo: Connect to API and run sample commands
 */
async function main() {
  const client = new RoaminControlClient();

  try {
    // Get status
    console.log("[*] Fetching status...");
    const status = await client.getStatus();
    console.log("[+] Status:", JSON.stringify(status, null, 2));

    // List models
    console.log("\n[*] Fetching models...");
    const models = await client.listModels();
    console.log("[+] Models:", JSON.stringify(models, null, 2));

    // List plugins
    console.log("\n[*] Fetching plugins...");
    const plugins = await client.listPlugins();
    console.log("[+] Plugins:", JSON.stringify(plugins, null, 2));

    // Get task history
    console.log("\n[*] Fetching task history...");
    const tasks = await client.getTaskHistory(10);
    console.log("[+] Tasks:", JSON.stringify(tasks, null, 2));

    // Listen for events (run for 5 seconds as demo)
    console.log("\n[*] Listening for events (5s timeout)...");
    const ws = client.listenEvents(
      (event) => {
        // Handle individual events here
      },
      (error) => {
        console.error("[!] Event listener error:", error);
      }
    );

    // Close after 5 seconds
    setTimeout(() => {
      ws.close();
    }, 5000);
  } catch (error) {
    console.error("[!] Error:", error.message);
    console.error("    Is Control API running at http://127.0.0.1:8765?");
  }
}

// Run demo if this is the main module (Node.js)
if (typeof module !== "undefined" && require.main === module) {
  main();
}

// Export for use as module
if (typeof module !== "undefined") {
  module.exports = RoaminControlClient;
}
