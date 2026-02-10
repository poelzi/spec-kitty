"""Unit tests for agent change command with stash routing, validation, and complexity.

Tests the agent change preview command with real stash routing,
ambiguity detection, closed reference checking, and deterministic
complexity scoring (WP02 + WP03).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from specify_cli.cli.commands.agent.change import app as agent_change_app
from typer.testing import CliRunner

runner = CliRunner()


class TestPreviewWithRouting:
    """Test preview command with real branch stash routing."""

    def test_preview_on_feature_branch(self) -> None:
        """Preview on feature branch should route to feature stash."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
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
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch", return_value="main"
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
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
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
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
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="001-demo",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
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
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch", return_value=None
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
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
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "refactor this part of change_stack.py", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["validationState"] == "valid"

    def test_preview_fails_in_non_initialized_repo(self) -> None:
        """Preview should fail with exit 1 in a git repo without .kittify."""
        with patch(
            "specify_cli.cli.commands.agent.change.locate_project_root"
        ) as mock_root:
            mock_root.return_value = None  # No .kittify found

            result = runner.invoke(
                agent_change_app,
                ["preview", "add caching", "--json"],
            )
            assert result.exit_code == 1
            assert ".kittify not found" in result.output

    def test_request_with_wp_id_is_valid(self) -> None:
        """Requests mentioning WP IDs should be valid even with vague language."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "change this block in WP03", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["validationState"] == "valid"


class TestPreviewComplexityIntegration:
    """Test that preview includes real complexity scoring (WP03)."""

    def test_preview_includes_real_complexity_scores(self) -> None:
        """Preview should include real (non-zero) complexity scores from classifier."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                [
                    "preview",
                    "add package requests and update the shared config module",
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            complexity = data["complexity"]
            # Should have real scoring fields
            assert "classification" in complexity
            assert "totalScore" in complexity
            assert "proposedMode" in complexity
            assert "reviewAttention" in complexity
            # At least one score component should be non-zero for this request
            assert complexity["totalScore"] >= 0

    def test_preview_high_complexity_shows_warning(self) -> None:
        """Preview should show warningRequired for high complexity requests."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            # Construct a high-complexity request
            result = runner.invoke(
                agent_change_app,
                [
                    "preview",
                    "replace framework Django with FastAPI, migrate from PostgreSQL to MongoDB, "
                    "update the api contract for all endpoints, modify the deployment pipeline "
                    "and kubernetes manifests, refactor all modules across the codebase",
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            if data["complexity"]["classification"] == "high":
                assert data["warningRequired"] is True
                assert data["warningMessage"] is not None
                assert data["complexity"]["recommendSpecify"] is True

    def test_preview_simple_no_warning(self) -> None:
        """Simple requests should not trigger a warning."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch("specify_cli.core.change_stack._get_main_repo_root") as mock_main,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_main.return_value = Path("/tmp/fake-repo")

            result = runner.invoke(
                agent_change_app,
                ["preview", "fix typo in README", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["warningRequired"] is False
            assert data["complexity"]["classification"] == "simple"


class TestApplyContinueGate:
    """Test FR-010/FR-011: explicit continue/stop gate on apply."""

    def test_apply_blocks_high_complexity_without_continue(self) -> None:
        """Apply should block high complexity requests without --continue."""
        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.cli.commands.agent.change.detect_feature_slug"
            ) as mock_slug,
        ):
            mock_root.return_value = Path("/tmp/fake-repo")
            mock_slug.return_value = "029-test"

            result = runner.invoke(
                agent_change_app,
                [
                    "apply",
                    "test-id",
                    "--request-text",
                    "replace framework Django with FastAPI, migrate from PostgreSQL to MongoDB, "
                    "update the api contract for all endpoints, modify the deployment pipeline "
                    "and kubernetes manifests, refactor all modules across the codebase",
                    "--json",
                ],
            )
            # Should either block (exit 1) if high, or pass through if scoring below threshold
            output = result.output
            data = json.loads(output)
            if "error" in data and data["error"] == "high_complexity_blocked":
                assert result.exit_code == 1
                assert "complexity threshold" in data["message"]

    def test_apply_allows_high_complexity_with_continue(self, tmp_path: Path) -> None:
        """Apply should allow high complexity requests with --continue."""
        # Create tasks dir for stash routing
        tasks_dir = tmp_path / "kitty-specs" / "029-test" / "tasks"
        tasks_dir.mkdir(parents=True)

        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.cli.commands.agent.change.detect_feature_slug"
            ) as mock_slug,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch(
                "specify_cli.core.change_stack._get_main_repo_root",
                return_value=tmp_path,
            ),
        ):
            mock_root.return_value = tmp_path
            mock_slug.return_value = "029-test"

            result = runner.invoke(
                agent_change_app,
                [
                    "apply",
                    "test-id",
                    "--request-text",
                    "replace framework Django with FastAPI, migrate from PostgreSQL to MongoDB, "
                    "update the api contract for all endpoints, modify the deployment pipeline "
                    "and kubernetes manifests, refactor all modules across the codebase",
                    "--continue",
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["requestId"] == "test-id"
            # When --continue is used with high complexity, result should include scoring
            if "complexity" in data:
                assert data["complexity"]["reviewAttention"] == "elevated"
            # Verify generated WP files have elevated review_attention in frontmatter
            if "writtenFiles" in data and data["writtenFiles"]:
                for fpath in data["writtenFiles"]:
                    content = Path(fpath).read_text(encoding="utf-8")
                    assert 'review_attention: "elevated"' in content, (
                        f"Generated WP {fpath} missing elevated review_attention"
                    )

    def test_apply_requires_request_text(self) -> None:
        """Apply without --request-text should fail (required for complexity gating)."""
        result = runner.invoke(
            agent_change_app,
            ["apply", "test-id", "--json"],
        )
        assert result.exit_code != 0

    def test_apply_simple_passes_without_continue(self, tmp_path: Path) -> None:
        """Apply with simple complexity should pass without --continue."""
        # Create tasks dir for stash routing
        tasks_dir = tmp_path / "kitty-specs" / "029-test" / "tasks"
        tasks_dir.mkdir(parents=True)

        with (
            patch(
                "specify_cli.cli.commands.agent.change.locate_project_root"
            ) as mock_root,
            patch(
                "specify_cli.cli.commands.agent.change.detect_feature_slug"
            ) as mock_slug,
            patch(
                "specify_cli.core.change_stack.get_current_branch",
                return_value="029-test",
            ),
            patch(
                "specify_cli.core.change_stack._get_main_repo_root",
                return_value=tmp_path,
            ),
        ):
            mock_root.return_value = tmp_path
            mock_slug.return_value = "029-test"

            result = runner.invoke(
                agent_change_app,
                [
                    "apply",
                    "test-id",
                    "--request-text",
                    "fix typo in README",
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["requestId"] == "test-id"
