# Spec: Dynamic Step Prioritization

## Requirements

### R1 — HIGH-priority steps execute before MED-priority steps
Steps with tools in the HIGH set (notify, take_screenshot, open_url, clipboard_write) receive
score 0 and execute before steps with score 1 (MED / default).

### R2 — LOW-priority steps execute after MED-priority steps
Steps with tools in the LOW set (memory_write, write_file, move_file, delete_file) receive
score 2 and execute after steps with score 1.

### R3 — Equal-priority steps retain LLM-declared order (stable sort)
Two steps with the same priority score execute in the order the LLM returned them.

### R4 — Unknown tools default to MED (score 1)
A step with a tool name not in either the HIGH or LOW set receives score 1. This is the same
implicit behaviour as before this change (all steps in LLM order).

### R5 — Action-text keywords apply when tool is null
A null-tool step whose "action" text contains "notif", "alert", "show", "display", or "open"
receives score 0. A null-tool step whose action contains "store", "save", "log", "record", or
"write" receives score 2.

---

## Scenarios

### Scenario 1: notify executes before memory_write
```
GIVEN a plan: [
  {"step": 1, "tool": "memory_write", "action": "store result", ...},
  {"step": 2, "tool": "notify", "action": "alert user", ...}
]
WHEN sorted(plan, key=AgentLoop._priority_score) is applied
THEN the execution order is: notify (step 2) then memory_write (step 1)
```

### Scenario 2: web_search (MED) stays between HIGH and LOW
```
GIVEN a plan: [
  {"step": 1, "tool": "memory_write", ...},
  {"step": 2, "tool": "web_search", ...},
  {"step": 3, "tool": "notify", ...}
]
WHEN sorted by _priority_score
THEN execution order is: notify, web_search, memory_write
```

### Scenario 3: equal-priority steps are stable
```
GIVEN a plan: [
  {"step": 1, "tool": "web_search", ...},
  {"step": 2, "tool": "memory_search", ...}
]
WHEN sorted by _priority_score (both score 1)
THEN web_search still executes before memory_search
```

### Scenario 4: unknown tool defaults to MED
```
GIVEN a step with tool="my_custom_tool" (not in HIGH or LOW sets)
WHEN _priority_score(step) is called
THEN it returns 1
```

### Scenario 5: null-tool step with notify keyword gets HIGH score
```
GIVEN a step with tool=null and action="show the user the result"
WHEN _priority_score(step) is called
THEN it returns 0 (contains "show")
```
