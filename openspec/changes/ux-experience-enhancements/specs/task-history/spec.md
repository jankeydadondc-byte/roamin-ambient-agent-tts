# Spec: Persistent Task History

## Requirements

### R1 — Completed task persisted with goal, status, and timestamps
When AgentLoop.run() completes, a row is inserted into `task_runs` with the goal text,
final status, task_type, started_at, finished_at, and step_count.

### R2 — Each step persisted with tool, params, outcome, and duration
For each step executed during a run, a row is inserted into `task_steps` with the tool name,
action description, params as JSON, outcome text, status, and duration in milliseconds.

### R3 — Failed and cancelled tasks recorded with correct status
When a task fails (model unreachable, feature not ready) or is cancelled (cancel event),
the `task_runs` row reflects the correct status ("failed" or "cancelled").

### R4 — Query by date range returns matching runs only
`get_task_runs(since="2026-04-05")` returns only task runs with `started_at >= since`.

### R5 — Keyword search matches goal and step action text
`search_task_history("web_search")` returns task runs whose goal or step actions contain
the keyword.

### R6 — /task-history REST endpoint returns persistent SQLite data
`GET /task-history` returns task runs from the SQLite database with optional query parameters
`?since=`, `?status=`, `?q=`.

### R7 — Logging failure does not abort task execution
If any task history write (create_task_run, add_task_step, finish_task_run) raises an
exception, the AgentLoop execution continues normally without interruption.

---

## Scenarios

### Scenario 1: Full task run persisted
```
GIVEN AgentLoop.run("search for python tips") executes successfully with 3 steps
WHEN the run completes
THEN task_runs contains a row with goal="search for python tips", status="completed", step_count=3
AND task_steps contains 3 rows linked to the task_run_id
AND each step row has tool, action, outcome, and duration_ms populated
```

### Scenario 2: Failed task recorded
```
GIVEN AgentLoop.run() fails because the model is unreachable
WHEN the run returns with status="failed"
THEN task_runs contains a row with status="failed" and finished_at set
AND step_count=0
```

### Scenario 3: Cancelled task recorded
```
GIVEN AgentLoop.run() is cancelled after step 2 of 4
WHEN the run returns with status="cancelled"
THEN task_runs contains a row with status="cancelled"
AND task_steps contains 2 rows (only the executed steps)
```

### Scenario 4: Query by date
```
GIVEN task_runs has entries from 2026-04-04 and 2026-04-05
WHEN get_task_runs(since="2026-04-05") is called
THEN only the 2026-04-05 entries are returned
```

### Scenario 5: Logging failure is non-fatal
```
GIVEN the SQLite database is locked or corrupted
WHEN AgentLoop.run() attempts to write task history
THEN the exception is caught silently
AND the task executes normally and returns a valid result
AND result["stored"] reflects memory write status (not task history status)
```
