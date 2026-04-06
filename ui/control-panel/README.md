# Roamin Control Prototype (SPA)

Quick start (requires Node.js/npm):

```bash
cd ui/control-panel
npm install
npm run dev
```

The prototype expects the Control API to be running at `http://127.0.0.1:8765` by default.
If you run the Python control API locally, use:

```bash
python -m pip install -r requirements.txt
python run_control_api.py
```

The SPA will connect to `/status` and `/ws/events` to show live updates.
