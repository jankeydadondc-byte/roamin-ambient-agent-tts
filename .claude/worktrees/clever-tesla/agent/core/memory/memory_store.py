import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "roamin_memory.db"


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or _DEFAULT_DB)
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
                    fact_name TEXT NOT NULL,
                    value TEXT NOT NULL
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO named_facts (fact_name, value)
                VALUES (?, ?)
            """,
                (fact_name, value),
            )
            conn.commit()
            return cursor.lastrowid

    # --- READ operations ---

    def get_conversation_history(self, session_id: str | None = None) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    """
                    SELECT * FROM conversation_history WHERE session_id = ?
                """,
                    (session_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM conversation_history
                """
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
