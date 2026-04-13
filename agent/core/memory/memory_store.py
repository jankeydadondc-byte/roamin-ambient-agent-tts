import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "roamin_memory.db"


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or _DEFAULT_DB)
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode — prevents 'database is locked' under concurrent readers/writers (#60)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    session_id TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    description TEXT NOT NULL,
                    screenshot_path TEXT
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS actions_taken (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    action_description TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    approval_status TEXT NOT NULL
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_name TEXT NOT NULL,
                    description TEXT NOT NULL
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS named_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_name TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL
                )
            """
            )
            # Migration: de-duplicate existing rows, then ensure unique index exists (#58)
            cursor.execute(
                """
                DELETE FROM named_facts WHERE id NOT IN (
                    SELECT MIN(id) FROM named_facts GROUP BY fact_name
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_named_facts_fact_name
                ON named_facts (fact_name)
                """
            )
            # --- Task history tables (Priority 6.3) ---
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_type TEXT,
                    started_at DATETIME NOT NULL,
                    finished_at DATETIME,
                    step_count INTEGER DEFAULT 0
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_run_id INTEGER NOT NULL,
                    step_number INTEGER NOT NULL,
                    tool TEXT,
                    action TEXT,
                    params_json TEXT,
                    outcome TEXT,
                    status TEXT NOT NULL,
                    started_at DATETIME,
                    finished_at DATETIME,
                    duration_ms INTEGER,
                    FOREIGN KEY (task_run_id) REFERENCES task_runs(id)
                )
            """
            )
            # --- HITL approval table ---
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_run_id INTEGER,
                    step_number INTEGER NOT NULL,
                    tool        TEXT,
                    action      TEXT NOT NULL,
                    params_json TEXT,
                    risk        TEXT DEFAULT 'high',
                    status      TEXT NOT NULL DEFAULT 'pending',
                    created_at  DATETIME NOT NULL,
                    resolved_at DATETIME
                )
            """
            )
            conn.commit()

    # --- CREATE operations ---

    def add_conversation_history(self, session_id: str, model_used: str, content: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_history (timestamp, session_id, model_used, content)
                VALUES (datetime('now'), ?, ?, ?)
            """,
                (session_id, model_used, content),
            )
            conn.commit()
            return cursor.lastrowid

    def add_observation(self, description: str, screenshot_path: str | None = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO observations (timestamp, description, screenshot_path)
                VALUES (datetime('now'), ?, ?)
            """,
                (description, screenshot_path),
            )
            conn.commit()
            return cursor.lastrowid

    def add_action_taken(self, action_description: str, outcome: str, approval_status: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO actions_taken (timestamp, action_description, outcome, approval_status)
                VALUES (datetime('now'), ?, ?, ?)
            """,
                (action_description, outcome, approval_status),
            )
            conn.commit()
            return cursor.lastrowid

    def add_user_pattern(self, pattern_name: str, description: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_patterns (pattern_name, description)
                VALUES (?, ?)
            """,
                (pattern_name, description),
            )
            conn.commit()
            return cursor.lastrowid

    def add_named_fact(self, fact_name: str, value: str) -> int:
        # INSERT OR REPLACE gives upsert semantics — updates value for existing fact_name (#58)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO named_facts (fact_name, value)
                VALUES (?, ?)
            """,
                (fact_name, value),
            )
            conn.commit()
            return cursor.lastrowid

    # --- READ operations ---

    def get_conversation_history(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        # Add LIMIT to prevent unbounded memory reads on long-running sessions (#59)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    """
                    SELECT * FROM conversation_history
                    WHERE session_id = ?
                    ORDER BY id DESC LIMIT ?
                """,
                    (session_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM conversation_history
                    ORDER BY id DESC LIMIT ?
                """,
                    (limit,),
                )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_observations(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM observations
            """
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_actions_taken(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM actions_taken
            """
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_user_patterns(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM user_patterns
            """
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_named_fact(self, fact_name: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM named_facts WHERE fact_name = ?
            """,
                (fact_name,),
            )
            row = cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None

    def get_all_named_facts(self) -> list[dict]:
        """Return all stored named facts."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM named_facts ORDER BY id DESC")
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # --- UPDATE operations ---

    def update_conversation_history(self, record_id: int, content: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversation_history
                SET content = ? WHERE id = ?
            """,
                (content, record_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_observation(self, record_id: int, description: str, screenshot_path: str | None = None) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if screenshot_path is not None:
                cursor.execute(
                    """
                    UPDATE observations
                    SET description = ?, screenshot_path = ? WHERE id = ?
                """,
                    (description, screenshot_path, record_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE observations
                    SET description = ? WHERE id = ?
                """,
                    (description, record_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def update_action_taken(self, record_id: int, outcome: str, approval_status: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE actions_taken
                SET outcome = ?, approval_status = ? WHERE id = ?
            """,
                (outcome, approval_status, record_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_user_pattern(self, record_id: int, pattern_name: str, description: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_patterns
                SET pattern_name = ?, description = ? WHERE id = ?
            """,
                (pattern_name, description, record_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_named_fact(self, record_id: int, value: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE named_facts
                SET value = ? WHERE id = ?
            """,
                (value, record_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- DELETE operations ---

    def delete_conversation_history(self, record_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM conversation_history WHERE id = ?
            """,
                (record_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_observation(self, record_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM observations WHERE id = ?
            """,
                (record_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_action_taken(self, record_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM actions_taken WHERE id = ?
            """,
                (record_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_user_pattern(self, record_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM user_patterns WHERE id = ?
            """,
                (record_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_named_fact(self, record_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM named_facts WHERE id = ?
            """,
                (record_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- Task history operations (Priority 6.3) ---

    def create_task_run(self, goal: str, task_type: str) -> int:
        """Create a new task run record. Returns the row id."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_runs (goal, status, task_type, started_at)
                VALUES (?, 'started', ?, datetime('now'))
            """,
                (goal, task_type),
            )
            conn.commit()
            return cursor.lastrowid

    def add_task_step(
        self,
        task_run_id: int,
        step_number: int,
        tool: str | None,
        action: str | None,
        params_json: str | None,
        outcome: str | None,
        status: str,
        duration_ms: int | None = None,
    ) -> int:
        """Record a single step within a task run."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_steps
                    (task_run_id, step_number, tool, action, params_json,
                     outcome, status, started_at, finished_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?)
            """,
                (task_run_id, step_number, tool, action, params_json, outcome, status, duration_ms),
            )
            conn.commit()
            return cursor.lastrowid

    def finish_task_run(self, task_run_id: int, status: str, step_count: int) -> bool:
        """Mark a task run as finished with final status and step count."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE task_runs
                SET status = ?, step_count = ?, finished_at = datetime('now')
                WHERE id = ?
            """,
                (status, step_count, task_run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_task_runs(
        self,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        since: str | None = None,
        task_type: str | None = None,
    ) -> list[dict]:
        """Query task runs with optional filters and pagination."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM task_runs WHERE 1=1"
            params: list = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if since:
                query += " AND started_at >= ?"
                params.append(since)
            if task_type:
                query += " AND task_type = ?"
                params.append(task_type)
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def count_task_runs(
        self,
        status: str | None = None,
        since: str | None = None,
        task_type: str | None = None,
    ) -> int:
        """Return total count of task runs matching optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM task_runs WHERE 1=1"
            params: list = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if since:
                query += " AND started_at >= ?"
                params.append(since)
            if task_type:
                query += " AND task_type = ?"
                params.append(task_type)
            cursor.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_task_steps(self, task_run_id: int) -> list[dict]:
        """Get all steps for a given task run."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM task_steps WHERE task_run_id = ? ORDER BY step_number",
                (task_run_id,),
            )
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def search_task_history(self, keyword: str) -> list[dict]:
        """Search task runs by keyword in goal or step action text."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            like_pat = f"%{keyword}%"
            cursor.execute(
                """
                SELECT DISTINCT tr.* FROM task_runs tr
                LEFT JOIN task_steps ts ON tr.id = ts.task_run_id
                WHERE tr.goal LIKE ? OR ts.action LIKE ?
                ORDER BY tr.id DESC
            """,
                (like_pat, like_pat),
            )
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def cleanup_old_task_runs(self, older_than_hours: int = 24) -> int:
        """Delete completed/failed task_runs older than given hours via MemoryStore (#8).

        Returns number of rows deleted.
        """
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            # Ensure table exists before attempting delete
            cur_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_runs'")
            if cur_check.fetchone() is None:
                return 0
            try:
                cur = conn.execute(
                    "DELETE FROM task_runs WHERE status IN ('completed', 'failed', 'partial')" " AND started_at < ?",
                    (cutoff,),
                )
                return cur.rowcount
            except sqlite3.OperationalError:
                # Table may not exist on fresh install — not an error
                return 0

    # --- HITL pending approval operations ---

    def create_pending_approval(
        self,
        task_run_id: int | None,
        step_number: int,
        tool: str | None,
        action: str,
        params_json: str | None,
        risk: str = "high",
    ) -> int:
        """Store a blocked step awaiting user approval. Returns the row id."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pending_approvals
                    (task_run_id, step_number, tool, action, params_json, risk, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                """,
                (task_run_id, step_number, tool, action, params_json, risk),
            )
            conn.commit()
            return cursor.lastrowid

    def get_pending_approval(self, approval_id: int) -> dict | None:
        """Load a single pending approval record by id."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_approvals WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))

    def resolve_approval(self, approval_id: int, status: str) -> bool:
        """Mark an approval as 'approved' or 'denied'. Returns True if a row was updated."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE pending_approvals
                SET status = ?, resolved_at = datetime('now')
                WHERE id = ?
                """,
                (status, approval_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_approvals(self) -> list[dict]:
        """Return all unresolved (pending) approvals."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_approvals WHERE status = 'pending' ORDER BY id DESC")
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def poll_approval_resolution(self, approval_id: int, timeout: int = 60) -> dict:
        """Poll pending_approvals every second until resolved or timeout elapses.

        Returns a dict with 'status' ('approved', 'denied', or 'timeout') and 'reason'.
        Reuses get_pending_approval() — no additional DB schema needed.
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = self.get_pending_approval(approval_id)
            if row and row.get("status") not in ("pending", None):
                return {"status": row["status"], "reason": row.get("resolved_by", "")}
            time.sleep(1)
        return {"status": "timeout", "reason": "approval_timeout"}
