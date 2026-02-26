"""Unit tests for spec_commit_policy module.

Tests cover:
- T015: Manual-edit detection (detect_manual_edits)
- T015: Commit policy (commit_spec_changes)
- T016: Auto-push behavior
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from specify_cli.core.spec_commit_policy import (
    MANUAL_EDIT_POLICY_ENV,
    SpecCommitAction,
    commit_with_policy,
    commit_spec_changes,
    detect_manual_edits,
    resolve_manual_edit_policy,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Create a minimal git worktree directory."""
    wt = tmp_path / "spec-worktree"
    wt.mkdir()
    return wt


# ============================================================================
# T015 - SpecCommitAction dataclass
# ============================================================================


class TestSpecCommitAction:
    """Tests for SpecCommitAction data class."""

    def test_defaults(self) -> None:
        """SpecCommitAction has sensible defaults."""
        action = SpecCommitAction(action="skip")
        assert action.action == "skip"
        assert action.intended_files == []
        assert action.manual_files == []

    def test_all_fields(self) -> None:
        """SpecCommitAction captures all fields."""
        action = SpecCommitAction(
            action="include",
            intended_files=["spec.md", "plan.md"],
            manual_files=["manual.md"],
        )
        assert action.action == "include"
        assert action.intended_files == ["spec.md", "plan.md"]
        assert action.manual_files == ["manual.md"]


# ============================================================================
# T015 - detect_manual_edits
# ============================================================================


class TestDetectManualEdits:
    """Tests for detect_manual_edits()."""

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_no_changes(self, mock_run: MagicMock, worktree: Path) -> None:
        """Returns empty list when git status shows no changes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
        )
        result = detect_manual_edits(worktree, ["spec.md"])
        assert result == []

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_only_intended_changes(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns empty list when all changes are in intended list."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M spec.md\n M plan.md\n",
        )
        result = detect_manual_edits(worktree, ["spec.md", "plan.md"])
        assert result == []

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_detects_manual_edits(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns files not in the intended list."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M spec.md\n M manual-edit.md\n?? new-file.txt\n",
        )
        result = detect_manual_edits(worktree, ["spec.md"])
        assert "manual-edit.md" in result
        assert "new-file.txt" in result
        assert "spec.md" not in result

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_handles_renames(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Handles git rename output (old -> new)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="R  old.md -> new.md\n M spec.md\n",
        )
        result = detect_manual_edits(worktree, ["spec.md"])
        assert "new.md" in result
        assert len(result) == 1

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_git_status_failure(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns empty list when git status fails."""
        mock_run.return_value = MagicMock(
            returncode=128,
            stderr="fatal: not a git repository",
        )
        result = detect_manual_edits(worktree, ["spec.md"])
        assert result == []

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_normalises_path_comparison(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Normalises paths for comparison (strips ./ prefix)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M ./spec.md\n",
        )
        result = detect_manual_edits(worktree, ["spec.md"])
        assert result == []

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_intended_with_leading_dot_slash(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Intended files with ./ prefix match git output without it."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M spec.md\n",
        )
        result = detect_manual_edits(worktree, ["./spec.md"])
        assert result == []


# ============================================================================
# T015 - resolve_manual_edit_policy
# ============================================================================


class TestResolveManualEditPolicy:
    """Tests for resolve_manual_edit_policy()."""

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_no_manual_edits_returns_include(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = []

        action = resolve_manual_edit_policy(worktree, ["spec.md"])

        assert action.action == "include"
        assert action.manual_files == []
        assert action.intended_files == ["spec.md"]

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_default_policy_is_skip_when_manual_edits_exist(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        action = resolve_manual_edit_policy(worktree, ["spec.md"])

        assert action.action == "skip"
        assert action.manual_files == ["manual.md"]

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_manual_policy_argument_include(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        action = resolve_manual_edit_policy(
            worktree,
            ["spec.md"],
            manual_policy="include",
        )

        assert action.action == "include"

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_manual_policy_argument_abort(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        action = resolve_manual_edit_policy(
            worktree,
            ["spec.md"],
            manual_policy="abort",
        )

        assert action.action == "abort"

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_env_override_used_when_no_argument(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        with patch.dict("os.environ", {MANUAL_EDIT_POLICY_ENV: "include"}):
            action = resolve_manual_edit_policy(worktree, ["spec.md"])

        assert action.action == "include"

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    def test_invalid_env_value_falls_back_to_skip(
        self, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        with patch.dict("os.environ", {MANUAL_EDIT_POLICY_ENV: "INVALID"}):
            action = resolve_manual_edit_policy(worktree, ["spec.md"])

        assert action.action == "skip"

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    @patch("builtins.input", side_effect=["x", "abort"])
    def test_interactive_prompt_retries_until_valid(
        self, _mock_input: MagicMock, mock_detect: MagicMock, worktree: Path
    ) -> None:
        mock_detect.return_value = ["manual.md"]

        action = resolve_manual_edit_policy(
            worktree,
            ["spec.md"],
            interactive=True,
        )

        assert action.action == "abort"


# ============================================================================
# T015 - commit_with_policy
# ============================================================================


class TestCommitWithPolicy:
    """Tests for commit_with_policy()."""

    @patch("specify_cli.core.spec_commit_policy.commit_spec_changes")
    @patch("specify_cli.core.spec_commit_policy.resolve_manual_edit_policy")
    def test_include_policy_stages_manual_edits(
        self,
        mock_resolve: MagicMock,
        mock_commit: MagicMock,
        worktree: Path,
    ) -> None:
        mock_resolve.return_value = SpecCommitAction(
            action="include",
            intended_files=["spec.md"],
            manual_files=["manual.md"],
        )
        mock_commit.return_value = True

        ok, action = commit_with_policy(
            worktree_path=worktree,
            intended_files=["spec.md"],
            message="test",
        )

        assert ok is True
        assert action.action == "include"
        mock_commit.assert_called_once_with(
            worktree_path=worktree,
            intended_files=["spec.md"],
            message="test",
            include_manual=True,
            auto_push=False,
            remote="origin",
        )

    @patch("specify_cli.core.spec_commit_policy.commit_spec_changes")
    @patch("specify_cli.core.spec_commit_policy.resolve_manual_edit_policy")
    def test_skip_policy_excludes_manual_edits(
        self,
        mock_resolve: MagicMock,
        mock_commit: MagicMock,
        worktree: Path,
    ) -> None:
        mock_resolve.return_value = SpecCommitAction(
            action="skip",
            intended_files=["spec.md"],
            manual_files=["manual.md"],
        )
        mock_commit.return_value = True

        ok, action = commit_with_policy(
            worktree_path=worktree,
            intended_files=["spec.md"],
            message="test",
        )

        assert ok is True
        assert action.action == "skip"
        mock_commit.assert_called_once_with(
            worktree_path=worktree,
            intended_files=["spec.md"],
            message="test",
            include_manual=False,
            auto_push=False,
            remote="origin",
        )

    @patch("specify_cli.core.spec_commit_policy.commit_spec_changes")
    @patch("specify_cli.core.spec_commit_policy.resolve_manual_edit_policy")
    def test_abort_policy_skips_commit_and_returns_false(
        self,
        mock_resolve: MagicMock,
        mock_commit: MagicMock,
        worktree: Path,
    ) -> None:
        mock_resolve.return_value = SpecCommitAction(
            action="abort",
            intended_files=["spec.md"],
            manual_files=["manual.md"],
        )

        ok, action = commit_with_policy(
            worktree_path=worktree,
            intended_files=["spec.md"],
            message="test",
        )

        assert ok is False
        assert action.action == "abort"
        mock_commit.assert_not_called()


# ============================================================================
# T015 - commit_spec_changes
# ============================================================================


class TestCommitSpecChanges:
    """Tests for commit_spec_changes()."""

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_successful_commit(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Successfully stages and commits intended files."""
        # git add succeeds, git commit succeeds
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md", "plan.md"],
            message="Add spec and plan",
        )
        assert result is True

        # Should have called git add for each file + git commit
        calls = mock_run.call_args_list
        add_calls = [c for c in calls if c[0][0][0:2] == ["git", "add"]]
        commit_calls = [c for c in calls if c[0][0][0:2] == ["git", "commit"]]
        assert len(add_calls) == 2
        assert len(commit_calls) == 1

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_nothing_to_commit(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns True when nothing to commit."""
        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(
                    returncode=1,
                    stdout="nothing to commit",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
        )
        assert result is True

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_commit_failure(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns False when commit fails."""
        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="fatal: error",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
        )
        assert result is False

    def test_nonexistent_worktree(self, tmp_path: Path) -> None:
        """Returns False for nonexistent worktree path."""
        result = commit_spec_changes(
            tmp_path / "nonexistent",
            intended_files=["spec.md"],
            message="test",
        )
        assert result is False

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_empty_files_list(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Returns True with empty intended files list (no-op)."""
        result = commit_spec_changes(
            worktree,
            intended_files=[],
            message="test",
        )
        assert result is True
        mock_run.assert_not_called()

    @patch("specify_cli.core.spec_commit_policy.detect_manual_edits")
    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_include_manual_edits(
        self,
        mock_run: MagicMock,
        mock_detect: MagicMock,
        worktree: Path,
    ) -> None:
        """When include_manual=True, manual edits are also staged."""
        mock_detect.return_value = ["manual.md"]
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            include_manual=True,
        )
        assert result is True
        mock_detect.assert_called_once_with(worktree, ["spec.md"])

        # Should have staged both spec.md and manual.md
        add_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][0:2] == ["git", "add"]
        ]
        staged_files = [c[0][0][2] for c in add_calls]
        assert "spec.md" in staged_files
        assert "manual.md" in staged_files


# ============================================================================
# T016 - Auto-push
# ============================================================================


class TestAutoPush:
    """Tests for auto-push behavior in commit_spec_changes."""

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_auto_push_on_success(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Pushes to remote after successful commit when auto_push=True."""
        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:3] == ["git", "branch", "--show-current"]:
                return MagicMock(returncode=0, stdout="kitty-specs\n", stderr="")
            if cmd[0:2] == ["git", "push"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            auto_push=True,
        )
        assert result is True

        # Verify push was called
        push_calls = [
            c for c in mock_run.call_args_list
            if len(c[0][0]) >= 2 and c[0][0][0:2] == ["git", "push"]
        ]
        assert len(push_calls) == 1
        assert push_calls[0][0][0] == ["git", "push", "origin", "kitty-specs"]

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_no_push_when_auto_push_false(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Does not push when auto_push=False (default)."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            auto_push=False,
        )
        assert result is True

        # No push calls
        push_calls = [
            c for c in mock_run.call_args_list
            if len(c[0][0]) >= 2 and c[0][0][0:2] == ["git", "push"]
        ]
        assert len(push_calls) == 0

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_push_failure_does_not_corrupt_commit(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Push failure returns True (commit still succeeded)."""
        call_count = 0

        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:3] == ["git", "branch", "--show-current"]:
                return MagicMock(returncode=0, stdout="kitty-specs\n", stderr="")
            if cmd[0:2] == ["git", "push"]:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="error: failed to push",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            auto_push=True,
        )
        # Commit succeeded; push failure is non-fatal
        assert result is True

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_custom_remote(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Push uses the specified remote name."""
        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:3] == ["git", "branch", "--show-current"]:
                return MagicMock(returncode=0, stdout="kitty-specs\n", stderr="")
            if cmd[0:2] == ["git", "push"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            auto_push=True,
            remote="upstream",
        )
        assert result is True

        push_calls = [
            c for c in mock_run.call_args_list
            if len(c[0][0]) >= 2 and c[0][0][0:2] == ["git", "push"]
        ]
        assert len(push_calls) == 1
        assert push_calls[0][0][0] == ["git", "push", "upstream", "kitty-specs"]

    @patch("specify_cli.core.spec_commit_policy.subprocess.run")
    def test_no_push_on_commit_failure(
        self, mock_run: MagicMock, worktree: Path
    ) -> None:
        """Does not attempt push when commit fails."""
        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["git", "add"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[0:2] == ["git", "commit"]:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="fatal: error",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        result = commit_spec_changes(
            worktree,
            intended_files=["spec.md"],
            message="test",
            auto_push=True,
        )
        assert result is False

        # No push calls since commit failed
        push_calls = [
            c for c in mock_run.call_args_list
            if len(c[0][0]) >= 2 and c[0][0][0:2] == ["git", "push"]
        ]
        assert len(push_calls) == 0
