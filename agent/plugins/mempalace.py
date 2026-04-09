"""MemPalace plugin — semantic memory search, auto-discovered from agent/plugins/.

Phase 1 (plugin mode): registers mempalace_status and mempalace_search tools in the
Roamin tool registry. LM Studio sees them alongside all other Roamin tools.

Phase 2 (standalone/auto mode): also launches the mempalace MCP server subprocess so
Claude Code, Cursor, or any MCP client can connect to all 26 built-in MCP tools.

Mode is controlled via the ROAMIN_MEMPALACE_MODE env var (default: plugin).
Palace data path is controlled via ROAMIN_MEMPALACE_PATH env var.

Rename to _mempalace.py to disable without deleting.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PALACE_PATH = Path(
    os.environ.get(
        "ROAMIN_MEMPALACE_PATH",
        r"C:\AI\roamin-ambient-agent-tts\mem_palace_data",
    )
)
# plugin = register tools in Roamin registry (default, Phase 1)
# standalone = only start MCP server, skip tool registration (Phase 2)
# auto = both: register tools AND start MCP server
_MODE = os.environ.get("ROAMIN_MEMPALACE_MODE", "plugin")


class Plugin:
    """MemPalace plugin — adds semantic memory search to Roamin."""

    name = "mempalace_memory"

    def __init__(self) -> None:
        self._mcp_proc: subprocess.Popen | None = None

    def on_load(self, registry) -> None:
        """Register tools and/or start MCP server based on mode."""
        if _MODE in ("plugin", "auto"):
            registry.register(
                name="mempalace_status",
                description=(
                    "Show MemPalace filing statistics — wings, rooms, and drawer counts. "
                    "Use to check what memories are stored and confirm the palace is initialized."
                ),
                risk="low",
                params={},
                implementation=self._status,
            )
            registry.register(
                name="mempalace_search",
                description=(
                    "Semantic search across MemPalace memories. Returns the top 5 most "
                    "relevant past conversations, decisions, or facts matching the query."
                ),
                risk="low",
                params={"query": "str"},
                implementation=self._search,
            )

        if _MODE in ("standalone", "auto"):
            self._start_mcp_server()

    def on_unload(self) -> None:
        """Terminate MCP server subprocess if running (Phase 2 cleanup)."""
        if self._mcp_proc is not None:
            try:
                self._mcp_proc.terminate()
                logger.info("MemPalace MCP server terminated")
            except Exception as e:
                logger.debug("MemPalace MCP server terminate failed (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _status(self, params: dict) -> dict:
        """Show palace filing statistics via the mempalace CLI."""
        if not _PALACE_PATH.exists():
            return {
                "success": False,
                "error": (
                    f"Palace not initialized at {_PALACE_PATH}. "
                    f"Run: mempalace init <project_dir> --palace {_PALACE_PATH}"
                ),
            }
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mempalace", "--palace", str(_PALACE_PATH), "status"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout or result.stderr
            return {"success": True, "result": output.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _search(self, params: dict) -> dict:
        """Semantic search using mempalace.searcher.search_memories."""
        query = (params or {}).get("query", "").strip()
        if not query:
            return {"success": False, "error": "query is required"}
        if not _PALACE_PATH.exists():
            return {
                "success": False,
                "error": (
                    f"Palace not initialized at {_PALACE_PATH}. "
                    f"Run: mempalace init <project_dir> --palace {_PALACE_PATH}"
                ),
            }
        try:
            from mempalace.searcher import search_memories

            results = search_memories(query, palace_path=str(_PALACE_PATH), n_results=5)
            # search_memories returns {"query": ..., "filters": ..., "results": [...]}
            # on error it returns {"error": ..., "hint": ...}
            if "error" in results:
                return {"success": False, "error": results["error"], "hint": results.get("hint")}
            hits = results.get("results", [])
            if not hits:
                return {"success": True, "result": f"No memories found for: {query}"}
            lines = []
            for h in hits:
                doc = h.get("document") or h.get("text") or str(h)
                score = h.get("similarity") or h.get("score") or h.get("distance")
                score_str = f" (score: {score:.2f})" if isinstance(score, float) else ""
                lines.append(f"- {doc[:300]}{score_str}")
            return {"success": True, "result": "\n".join(lines)}
        except ImportError:
            return {"success": False, "error": "mempalace package not installed in this venv"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Phase 2: MCP server subprocess
    # ------------------------------------------------------------------

    def _start_mcp_server(self) -> None:
        """Start the mempalace MCP server as a background subprocess (Phase 2).

        Logs to logs/mempalace_mcp.log. Non-fatal — failure is logged and
        the plugin continues loading without the MCP server.
        """
        log_path = Path(__file__).parents[2] / "logs" / "mempalace_mcp.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(log_path, "a")  # noqa: WPS515 — subprocess needs persistent fd
            self._mcp_proc = subprocess.Popen(
                [sys.executable, "-m", "mempalace.mcp_server"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env={**os.environ, "MEMPALACE_PALACE": str(_PALACE_PATH)},
            )
            logger.info("MemPalace MCP server started (PID %d) → %s", self._mcp_proc.pid, log_path)
        except Exception as e:
            logger.error("MemPalace MCP server failed to start (non-fatal): %s", e)
