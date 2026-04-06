## ADDED Requirements

### Requirement: Cancel active agent run on second hotkey press

When `ctrl+space` is pressed while a wake cycle is already active AND the AgentLoop is currently executing steps, the system SHALL call `agent_loop.cancel()` to signal an orderly stop, and SHALL play a cancellation acknowledgment phrase via TTS.

#### Scenario: Second press cancels running agent loop

- **WHEN** `ctrl+space` fires while `_wake_lock` is held AND `_agent_running_event` is set
- **THEN** `agent_loop.cancel()` is called, a cancellation phrase is spoken in a background thread, and the hotkey handler returns

#### Scenario: Second press during STT recording is ignored

- **WHEN** `ctrl+space` fires while `_wake_lock` is held AND `_agent_running_event` is NOT set (e.g., during recording or TTS playback)
- **THEN** the press is silently dropped (existing "already in progress" behaviour is preserved)

#### Scenario: `cancel()` has no effect if AgentLoop already finished

- **WHEN** `agent_loop.cancel()` is called after all steps have completed
- **THEN** the call is a no-op; no error is raised and no extra TTS phrase is spoken

### Requirement: Agent running state tracked via threading.Event

`WakeListener` SHALL maintain a `threading.Event` named `_agent_running_event` that is set immediately before `AgentLoop.run()` is called and cleared immediately after it returns (including on exception).

#### Scenario: Flag set before AgentLoop.run

- **WHEN** `_on_wake` reaches the `agent_loop.run(goal)` call
- **THEN** `_agent_running_event` is set before the call and cleared in a `finally` block after it returns

#### Scenario: Flag cleared on exception

- **WHEN** `AgentLoop.run()` raises an exception
- **THEN** `_agent_running_event` is cleared in the `finally` block so subsequent wake presses are not treated as cancel presses
