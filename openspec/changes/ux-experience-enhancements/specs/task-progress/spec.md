# Spec: Task Progress Updates

## Requirements

### R1 — "Let me think..." spoken before planning
When AgentLoop.run() begins the planning phase, the on_progress callback emits a
`{"phase": "planning"}` event. The wake_listener handler speaks "Let me think..." via
a pre-cached TTS phrase.

### R2 — Step announcements for 3+ step plans
When the plan contains 3 or more steps, each step_start event triggers the handler to
speak "Step N of M" (e.g., "Step 2 of 4").

### R3 — No announcements for 1-2 step plans
When the plan contains 1 or 2 steps, step_start events do NOT trigger TTS announcements.
The plan completes quickly enough that announcements would be intrusive.

### R4 — on_progress=None preserves existing behavior
When `run()` is called without on_progress (or with on_progress=None), no progress events
are emitted. The return value and behavior are identical to the pre-change implementation.

### R5 — No progress after cancellation
When the cancel event is set, no further on_progress calls are made for steps beyond the
cancellation point.

---

## Scenarios

### Scenario 1: Planning phase spoken cue
```
GIVEN on_progress is provided and TTS is available
WHEN AgentLoop.run() enters the planning phase
THEN on_progress is called with {"phase": "planning", "detail": "Planning..."}
AND the handler speaks "Let me think..."
```

### Scenario 2: Multi-step progress announcements
```
GIVEN a plan with 4 steps is generated
AND on_progress is provided
WHEN the step loop begins executing
THEN on_progress is called before each step with {"phase": "step_start", "step": N, "total_steps": 4}
AND the handler speaks "Step 1 of 4", "Step 2 of 4", etc.
```

### Scenario 3: Short plan stays silent
```
GIVEN a plan with 2 steps is generated
AND on_progress is provided
WHEN the step loop begins executing
THEN on_progress is called with step_start events
BUT the handler does NOT speak step announcements (total_steps <= 2)
```

### Scenario 4: No callback provided
```
GIVEN on_progress is None (default)
WHEN AgentLoop.run() executes a goal
THEN no progress events are emitted
AND the result dict is identical to the pre-change behavior
```

### Scenario 5: Cancelled task stops progress
```
GIVEN on_progress is provided
AND the cancel event is set after step 2 of 4
WHEN the step loop checks the cancel event before step 3
THEN on_progress is NOT called for steps 3 or 4
AND the result status is "cancelled"
```
