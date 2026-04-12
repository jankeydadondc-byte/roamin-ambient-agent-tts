# Architecture Diagram — Control Panel (high level)

This diagram summarizes the runtime components for the Control Panel, the Control API, and event flow for installs and tasks.

```mermaid
flowchart LR
  subgraph UI
    A[SPA (Vite + React)\nComponents: Header, Sidebar, TaskHistory, PluginList]
  end

  subgraph Backend
    B[Control API (FastAPI)]
    C[Task Queue / Worker]
    D[Plugin Manager / Store]
  end

  A -- REST / HTTP --> B
  A -- WebSocket --> B
  B --> C
  C --> D
  D --> B
  B --> A

  style A fill:#f9f,stroke:#333,stroke-width:1px
  style B fill:#bbf,stroke:#333,stroke-width:1px
  style C fill:#fee,stroke:#333,stroke-width:1px
  style D fill:#efe,stroke:#333,stroke-width:1px
```

Notes:

- The SPA communicates via REST calls for control actions and uses a reconnecting WebSocket for real-time events (`task_update`, `plugin_event`, `log_line`).
- The Control API enqueues long-running operations to the Task Queue and emits `task_update` events to connected WS clients.
- The Plugin Manager persists installed plugin metadata and manifests (local store or DB) and is the authoritative source for `GET /plugins`.

Accepted diagram format: Mermaid flowchart. If you want a sequence diagram or component diagram, tell me which and I'll add it.
