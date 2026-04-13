# -*- coding: utf-8 -*-
"""
Package initialization for agent.core.

This module explicitly imports the AgentLoop class from the
`agent_loop` submodule so that it is available as an attribute of
`agent.core` when imported in test environments such as pytest. The
explicit import fixes a package‑level import resolution issue observed by
the test suite.
"""

from .agent_loop import AgentLoop  # noqa: F401
