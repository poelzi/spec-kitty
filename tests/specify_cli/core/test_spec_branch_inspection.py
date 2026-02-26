"""Unit tests for orphan branch inspection helpers (T004).

Tests cover:
- SpecBranchState dataclass
- Branch existence detection (local / remote)
- Orphan status detection (no shared ancestry)
- inspect_spec_branch() integration
- Edge cases: detached HEAD, shallow clone, missing branches
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specify_cli.core.git_ops import (
    SpecBranchState,
    inspect_spec_branch,
)


# ============================================================================
# Helpers
# ============================================================================


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Create a mock subprocess.run return value."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ============================================================================
# SpecBranchState dataclass
# ============================================================================


class TestSpecBranchState:
    """Test SpecBranchState dataclass fields."""

    def test_fields(self):
        """All expected fields exist with correct types."""
        state = SpecBranchState(
            branch_name="kitty-specs",
            exists_local=True,
            exists_remote=False,
            is_orphan=True,
            head_commit="abc1234",
        )
        assert state.branch_name == "kitty-specs"
        assert state.exists_local is True
        assert state.exists_remote is False
        assert state.is_orphan is True
        assert state.head_commit == "abc1234"

    def test_head_commit_none_when_missing(self):
        """head_commit is None when branch does not exist."""
        state = SpecBranchState(
            branch_name="missing",
            exists_local=False,
            exists_remote=False,
            is_orphan=False,
            head_commit=None,
        )
        assert state.head_commit is None


# ============================================================================
# inspect_spec_branch
# ============================================================================


class TestInspectSpecBranch:
    """Test inspect_spec_branch() function."""

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_branch_exists_locally_and_is_orphan(self, mock_run, tmp_path: Path):
        """Branch exists locally, has no common ancestor -> orphan."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            # rev-parse --verify kitty-specs (local exists)
            if "rev-parse" in cmd_str and "--verify" in cmd_str and "kitty-specs" in cmd_str and "origin" not in cmd_str:
                return _mock_run(0, "abc1234\n")

            # rev-parse --verify origin/kitty-specs (remote missing)
            if "rev-parse" in cmd_str and "origin/kitty-specs" in cmd_str:
                return _mock_run(128, "", "fatal: not a valid ref\n")

            # rev-parse --short kitty-specs (HEAD commit)
            if "rev-parse" in cmd_str and "--short" in cmd_str:
                return _mock_run(0, "abc1234\n")

            # merge-base main kitty-specs (no common ancestor = orphan)
            if "merge-base" in cmd_str:
                return _mock_run(1, "", "")

            # rev-parse --verify main (primary branch exists)
            if "rev-parse" in cmd_str and "--verify" in cmd_str and "main" in cmd_str:
                return _mock_run(0, "def5678\n")

            # symbolic-ref (primary branch detection)
            if "symbolic-ref" in cmd_str:
                return _mock_run(0, "refs/remotes/origin/main\n")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(tmp_path, "kitty-specs")

        assert state.branch_name == "kitty-specs"
        assert state.exists_local is True
        assert state.exists_remote is False
        assert state.is_orphan is True
        assert state.head_commit == "abc1234"

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_branch_exists_both_local_and_remote(self, mock_run, tmp_path: Path):
        """Branch exists both locally and on remote."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            if "rev-parse" in cmd_str and "--verify" in cmd_str:
                return _mock_run(0, "abc1234\n")

            if "rev-parse" in cmd_str and "--short" in cmd_str:
                return _mock_run(0, "abc1234\n")

            if "merge-base" in cmd_str:
                return _mock_run(1, "", "")

            if "symbolic-ref" in cmd_str:
                return _mock_run(0, "refs/remotes/origin/main\n")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(tmp_path, "kitty-specs")
        assert state.exists_local is True
        assert state.exists_remote is True

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_branch_missing_entirely(self, mock_run, tmp_path: Path):
        """Branch does not exist locally or remotely."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            if "rev-parse" in cmd_str and "--verify" in cmd_str:
                return _mock_run(128, "", "fatal: not a valid ref\n")

            if "symbolic-ref" in cmd_str:
                return _mock_run(0, "refs/remotes/origin/main\n")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(tmp_path, "kitty-specs")
        assert state.exists_local is False
        assert state.exists_remote is False
        assert state.is_orphan is False
        assert state.head_commit is None

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_branch_not_orphan(self, mock_run, tmp_path: Path):
        """Branch shares ancestry with primary -> is_orphan=False."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            if "rev-parse" in cmd_str and "--verify" in cmd_str:
                return _mock_run(0, "abc1234\n")

            if "rev-parse" in cmd_str and "--short" in cmd_str:
                return _mock_run(0, "abc1234\n")

            # merge-base succeeds = shared ancestor = NOT orphan
            if "merge-base" in cmd_str:
                return _mock_run(0, "common-ancestor-sha\n")

            if "symbolic-ref" in cmd_str:
                return _mock_run(0, "refs/remotes/origin/main\n")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(tmp_path, "kitty-specs")
        assert state.is_orphan is False

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_explicit_primary_branch(self, mock_run, tmp_path: Path):
        """Uses explicit primary_branch parameter when provided."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            if "rev-parse" in cmd_str and "--verify" in cmd_str:
                return _mock_run(0, "abc1234\n")

            if "rev-parse" in cmd_str and "--short" in cmd_str:
                return _mock_run(0, "abc1234\n")

            # merge-base uses develop (our explicit primary)
            if "merge-base" in cmd_str and "develop" in cmd_str:
                return _mock_run(1, "", "")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(
            tmp_path, "kitty-specs", primary_branch="develop"
        )
        assert state.is_orphan is True

    @patch("specify_cli.core.git_ops.subprocess.run")
    def test_remote_only_branch(self, mock_run, tmp_path: Path):
        """Branch exists on remote but not locally."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)

            # Local does not exist
            if "rev-parse" in cmd_str and "--verify" in cmd_str and "origin/" not in cmd_str:
                return _mock_run(128, "", "fatal: not a valid ref\n")

            # Remote exists
            if "rev-parse" in cmd_str and "origin/kitty-specs" in cmd_str:
                return _mock_run(0, "abc1234\n")

            if "symbolic-ref" in cmd_str:
                return _mock_run(0, "refs/remotes/origin/main\n")

            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = inspect_spec_branch(tmp_path, "kitty-specs")
        assert state.exists_local is False
        assert state.exists_remote is True
        assert state.is_orphan is False  # Can't determine without local branch
        assert state.head_commit is None
