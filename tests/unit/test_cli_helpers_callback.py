"""Tests for CLI root callback behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from specify_cli.cli.helpers import callback


def test_callback_runs_parallel_checkout_link_guard_for_subcommands() -> None:
    ctx = SimpleNamespace(invoked_subcommand="agent")

    with patch("specify_cli.cli.helpers.ensure_parallel_checkout_specs_link") as mock_guard:
        callback(ctx)

    mock_guard.assert_called_once()


def test_callback_skips_parallel_checkout_link_guard_for_init() -> None:
    ctx = SimpleNamespace(invoked_subcommand="init")

    with patch("specify_cli.cli.helpers.ensure_parallel_checkout_specs_link") as mock_guard:
        callback(ctx)

    mock_guard.assert_not_called()


def test_callback_swallow_link_guard_errors() -> None:
    ctx = SimpleNamespace(invoked_subcommand="agent")

    with patch(
        "specify_cli.cli.helpers.ensure_parallel_checkout_specs_link",
        side_effect=RuntimeError("boom"),
    ):
        callback(ctx)
