"""Tests for the unified chat engine pipeline — tasks 4.1–4.5."""

from unittest.mock import MagicMock, patch

from agent.core.chat_engine import build_memory_context, extract_and_store_fact, process_message

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_store(facts=None):
    """Return a MemoryStore mock with get_all_named_facts pre-configured."""
    store = MagicMock()
    store.get_all_named_facts.return_value = facts or []
    return store


def _make_mock_loop(tool_result=None):
    """Return a mock AgentLoop whose run() returns an empty step list."""
    loop = MagicMock()
    loop.run.return_value = {"status": "done", "steps": []}
    # registry.execute returns failure by default (no tool matched)
    loop.registry.execute.return_value = tool_result or {"success": False}
    return loop


def _make_mock_session():
    """Return a mock Session with an empty context block."""
    session = MagicMock()
    session.get_context_block.return_value = ""
    return session


# ---------------------------------------------------------------------------
# 4.2 — extract_and_store_fact
# ---------------------------------------------------------------------------


class TestExtractAndStoreFact:
    """Verify fact patterns are detected and persisted via MemoryManager."""

    def test_my_x_is_y_stored(self):
        """'my favorite color is blue' triggers a named_fact write."""
        mock_memory = MagicMock()
        result = extract_and_store_fact("my favorite color is blue", mock_memory)

        assert result is True
        mock_memory.write_to_memory.assert_called_once_with(
            "named_fact", {"fact_name": "favorite color", "value": "blue"}
        )

    def test_remember_variant_stored(self):
        """'remember that my birthday is April 5' also triggers storage."""
        mock_memory = MagicMock()
        result = extract_and_store_fact("remember that my birthday is April 5", mock_memory)

        assert result is True
        mock_memory.write_to_memory.assert_called_once()
        kwargs = mock_memory.write_to_memory.call_args[0]
        assert kwargs[0] == "named_fact"
        assert kwargs[1]["fact_name"] == "birthday"
        assert "april 5" in kwargs[1]["value"].lower()

    def test_plain_greeting_not_stored(self):
        """'hello' has no fact pattern — nothing written."""
        mock_memory = MagicMock()
        result = extract_and_store_fact("hello", mock_memory)

        assert result is False
        mock_memory.write_to_memory.assert_not_called()

    def test_question_not_stored(self):
        """'what time is it?' has no fact pattern — nothing written."""
        mock_memory = MagicMock()
        result = extract_and_store_fact("what time is it?", mock_memory)

        assert result is False
        mock_memory.write_to_memory.assert_not_called()

    def test_write_failure_returns_false(self):
        """Exception from MemoryManager is swallowed and returns False."""
        mock_memory = MagicMock()
        mock_memory.write_to_memory.side_effect = RuntimeError("db error")

        result = extract_and_store_fact("my mood is great", mock_memory)

        assert result is False


# ---------------------------------------------------------------------------
# 4.3 — build_memory_context
# ---------------------------------------------------------------------------


class TestBuildMemoryContext:
    """Verify ChromaDB results and named facts are woven into the context string."""

    def test_documents_appear_in_context(self):
        """ChromaDB results are joined into 'Relevant memories: ...'."""
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": ["doc alpha", "doc beta"]}

        with patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store()):
            context = build_memory_context("test query", mock_memory)

        assert "doc alpha" in context
        assert "doc beta" in context

    def test_named_facts_appear_in_context(self):
        """Named facts from MemoryStore are listed as 'Known facts about the user'."""
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        facts = [{"fact_name": "favorite color", "value": "blue"}]
        with patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store(facts)):
            context = build_memory_context("test query", mock_memory)

        assert "favorite color: blue" in context

    def test_both_docs_and_facts_in_context(self):
        """When both ChromaDB docs and named facts exist, both appear."""
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": ["memory fragment"]}

        facts = [{"fact_name": "name", "value": "Asherre"}]
        with patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store(facts)):
            context = build_memory_context("test query", mock_memory)

        assert "memory fragment" in context
        assert "name: Asherre" in context

    def test_empty_results_returns_empty_string(self):
        """No docs and no facts → empty context string."""
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        with patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store()):
            context = build_memory_context("test query", mock_memory)

        assert context == ""

    def test_chromadb_failure_is_swallowed(self):
        """Exception from search_memory is swallowed; facts still returned."""
        mock_memory = MagicMock()
        mock_memory.search_memory.side_effect = RuntimeError("chroma down")

        facts = [{"fact_name": "color", "value": "red"}]
        with patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store(facts)):
            context = build_memory_context("test query", mock_memory)

        assert "color: red" in context


# ---------------------------------------------------------------------------
# 4.4 — process_message: correct result construction
# ---------------------------------------------------------------------------


class TestProcessMessage:
    """process_message() calls router, updates session, and returns the reply."""

    def _run(self, message, router_reply="Here is my answer", facts=None, loop=None):
        """Execute process_message with all heavy dependencies mocked."""
        mock_session = _make_mock_session()
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        mock_router = MagicMock()
        mock_router.respond.return_value = router_reply

        mock_loop = loop or _make_mock_loop()

        with (
            patch("agent.core.chat_engine._get_chat_loop", return_value=mock_loop),
            patch("agent.core.memory.MemoryManager", return_value=mock_memory),
            patch("agent.core.model_router.ModelRouter", return_value=mock_router),
            patch("agent.core.voice.session.get_session", return_value=mock_session),
            patch(
                "agent.core.memory.memory_store.MemoryStore",
                return_value=_make_mock_store(facts),
            ),
        ):
            result = process_message(message)

        return result, mock_session, mock_router

    def test_returns_router_reply(self):
        """process_message returns the string from ModelRouter.respond()."""
        result, _, _ = self._run("what time is it?")
        assert result == "Here is my answer"

    def test_session_updated_with_reply(self):
        """session.add('assistant', reply) is called with the final reply."""
        result, mock_session, _ = self._run("what time is it?")
        mock_session.add.assert_called_once_with("assistant", result)

    def test_router_called_with_messages_list(self):
        """ModelRouter.respond() receives a messages list with system + user roles."""
        _, _, mock_router = self._run("test input")
        call_kwargs = mock_router.respond.call_args.kwargs
        messages = call_kwargs.get("messages", [])
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles

    def test_system_prompt_contains_layer2_sidecar(self):
        """System prompt contains the [Roamin Context] sidecar block."""
        _, _, mock_router = self._run("test input")
        call_kwargs = mock_router.respond.call_args.kwargs
        messages = call_kwargs.get("messages", [])
        system_msg = next(m["content"] for m in messages if m["role"] == "system")
        assert "[Roamin Context]" in system_msg

    def test_tool_context_injected_when_agentloop_runs(self):
        """Tool output from AgentLoop steps appears in the system prompt."""
        mock_loop = _make_mock_loop()
        mock_loop.run.return_value = {
            "status": "done",
            "steps": [{"status": "executed", "tool": "read_file", "outcome": "file contents here"}],
        }
        _, _, mock_router = self._run("read my notes", loop=mock_loop)
        call_kwargs = mock_router.respond.call_args.kwargs
        messages = call_kwargs.get("messages", [])
        system_msg = next(m["content"] for m in messages if m["role"] == "system")
        assert "file contents here" in system_msg


# ---------------------------------------------------------------------------
# 4.5 — process_message: fallback on empty / blank router reply
# ---------------------------------------------------------------------------


class TestProcessMessageFallback:
    """ModelRouter returning empty/blank string must produce a safe fallback reply."""

    def _run_empty(self, message):
        """Run process_message with a router that returns an empty string."""
        mock_session = _make_mock_session()
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        mock_router = MagicMock()
        mock_router.respond.return_value = ""

        with (
            patch("agent.core.chat_engine._get_chat_loop", return_value=_make_mock_loop()),
            patch("agent.core.memory.MemoryManager", return_value=mock_memory),
            patch("agent.core.model_router.ModelRouter", return_value=mock_router),
            patch("agent.core.voice.session.get_session", return_value=mock_session),
            patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store()),
        ):
            result = process_message(message)
        return result

    def test_empty_reply_returns_done(self):
        """Empty ModelRouter response → 'Done.' fallback."""
        result = self._run_empty("what is the capital of France?")
        assert result == "Done."

    def test_empty_reply_after_fact_stored_returns_got_it(self):
        """When a fact was stored and reply is empty → 'Got it.' fallback."""
        mock_session = _make_mock_session()
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        mock_router = MagicMock()
        mock_router.respond.return_value = ""

        with (
            patch("agent.core.chat_engine._get_chat_loop", return_value=_make_mock_loop()),
            patch("agent.core.memory.MemoryManager", return_value=mock_memory),
            patch("agent.core.model_router.ModelRouter", return_value=mock_router),
            patch("agent.core.voice.session.get_session", return_value=mock_session),
            patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store()),
        ):
            result = process_message("my favorite color is blue")

        assert result == "Got it."

    def test_whitespace_only_reply_returns_done(self):
        """Whitespace-only reply is treated as empty → 'Done.'."""
        mock_session = _make_mock_session()
        mock_memory = MagicMock()
        mock_memory.search_memory.return_value = {"documents": []}

        mock_router = MagicMock()
        # Whitespace survives the regex pipeline unchanged, then strip() → ""
        mock_router.respond.return_value = "   "

        with (
            patch("agent.core.chat_engine._get_chat_loop", return_value=_make_mock_loop()),
            patch("agent.core.memory.MemoryManager", return_value=mock_memory),
            patch("agent.core.model_router.ModelRouter", return_value=mock_router),
            patch("agent.core.voice.session.get_session", return_value=mock_session),
            patch("agent.core.memory.memory_store.MemoryStore", return_value=_make_mock_store()),
        ):
            result = process_message("tell me something")

        assert result == "Done."
