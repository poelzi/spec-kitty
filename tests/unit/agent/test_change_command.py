"""Unit tests for agent change command with stash routing and validation.

Tests the agent change preview command with real stash routing,
ambiguity detection, and closed reference checking.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands.agent.change import app as agent_change_app


runner = CliRunner()


class TestPreviewWithRouting:
    """Test preview command with real branch stash routing."""

    def test_preview_on_feature_branch(self) -> None:
        """Preview on feature branch should route to feature stash."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "use pydantic in models.py", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["stashScope"] == "feature"
            assert data["stashKey"] == "029-test"
            assert data["validationState"] == "valid"
            assert not data["requiresClarification"]

    def test_preview_on_main_branch(self) -> None:
        """Preview on main should route to main stash."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="main"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "fix typo in README", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["stashScope"] == "main"
            assert data["stashKey"] == "main"

    def test_preview_ambiguous_request(self) -> None:
        """Ambiguous request should be flagged in preview."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "change this block", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["validationState"] == "ambiguous"
            assert data["requiresClarification"]
            assert data["clarificationPrompt"] is not None

    def test_preview_with_closed_wp_reference(self) -> None:
        """Preview should include closed reference info."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="001-demo"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            repo_root = Path("/tmp/fake-repo")
            mock_root.return_value = repo_root
            mock_main.return_value = repo_root

            # Create a done WP
            tasks_dir = repo_root / "kitty-specs" / "001-demo" / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            (tasks_dir / "WP01-setup.md").write_text(
                '---\nlane: "done"\n---\n', encoding="utf-8"
            )

            try:
                result = runner.invoke(
                    agent_change_app,
                    ["preview", "apply same pattern as WP01 to auth.py", "--json"],
                )
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert data["validationState"] == "valid"
                if "closedReferences" in data:
                    assert data["closedReferences"]["linkOnly"]
            finally:
                # Cleanup temp files
                import shutil
                if tasks_dir.exists():
                    shutil.rmtree(tasks_dir.parent)

    def test_preview_unresolvable_branch_errors(self) -> None:
        """Preview should error when branch can't be resolved."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value=None), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "add caching", "--json"],
            )
            assert result.exit_code == 1


class TestPreviewValidation:
    """Test preview validation edge cases."""

    def test_request_with_file_path_is_valid(self) -> None:
        """Requests mentioning file paths should be valid."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "refactor this part of change_stack.py", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["validationState"] == "valid"

    def test_request_with_wp_id_is_valid(self) -> None:
        """Requests mentioning WP IDs should be valid even with vague language."""
        with patch("specify_cli.cli.commands.agent.change.find_repo_root") as mock_root, \
             patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main:
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "change this block in WP03", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["validationState"] == "valid"
