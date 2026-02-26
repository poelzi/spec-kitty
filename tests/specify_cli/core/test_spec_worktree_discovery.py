"""Unit tests for spec worktree discovery helpers (T005).

Tests cover:
- SpecWorktreeState dataclass and health constants
- Porcelain output parsing
- discover_spec_worktree() health status determination
- Edge cases: missing dirs, wrong branch, path conflicts
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specify_cli.core.spec_storage_config import SpecStorageConfig
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    HEALTH_PATH_CONFLICT,
    HEALTH_WRONG_BRANCH,
    SpecWorktreeState,
    _parse_worktree_list,
    discover_spec_worktree,
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
# Health status constants
# ============================================================================


class TestHealthConstants:
    """Test health status constants are the expected values."""

    def test_healthy(self):
        assert HEALTH_HEALTHY == "healthy"

    def test_missing_path(self):
        assert HEALTH_MISSING_PATH == "missing_path"

    def test_missing_registration(self):
        assert HEALTH_MISSING_REGISTRATION == "missing_registration"

    def test_wrong_branch(self):
        assert HEALTH_WRONG_BRANCH == "wrong_branch"

    def test_path_conflict(self):
        assert HEALTH_PATH_CONFLICT == "path_conflict"


# ============================================================================
# SpecWorktreeState
# ============================================================================


class TestSpecWorktreeState:
    """Test SpecWorktreeState dataclass."""

    def test_healthy_state(self):
        state = SpecWorktreeState(
            path="/repo/kitty-specs",
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_HEALTHY,
        )
        assert state.registered is True
        assert state.health_status == "healthy"

    def test_missing_registration_state(self):
        state = SpecWorktreeState(
            path="/repo/kitty-specs",
            registered=False,
            branch_name=None,
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_MISSING_REGISTRATION,
        )
        assert state.registered is False
        assert state.branch_name is None


# ============================================================================
# Porcelain parser
# ============================================================================


class TestParseWorktreeList:
    """Test _parse_worktree_list() porcelain output parser."""

    def test_single_main_worktree(self):
        """Parses a single main worktree entry."""
        output = (
            "worktree /repo\n"
            "HEAD abc1234def5678\n"
            "branch refs/heads/main\n"
            "\n"
        )
        entries = _parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].path == "/repo"
        assert entries[0].head == "abc1234def5678"
        assert entries[0].branch == "main"

    def test_multiple_worktrees(self):
        """Parses multiple worktree entries."""
        output = (
            "worktree /repo\n"
            "HEAD aaa\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo/kitty-specs\n"
            "HEAD bbb\n"
            "branch refs/heads/kitty-specs\n"
            "\n"
        )
        entries = _parse_worktree_list(output)
        assert len(entries) == 2
        assert entries[0].branch == "main"
        assert entries[1].branch == "kitty-specs"
        assert entries[1].path == "/repo/kitty-specs"

    def test_detached_head(self):
        """Parses detached HEAD worktree."""
        output = (
            "worktree /repo/.worktrees/temp\n"
            "HEAD ccc\n"
            "detached\n"
            "\n"
        )
        entries = _parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].is_detached is True
        assert entries[0].branch is None

    def test_bare_repo(self):
        """Parses bare repository entry."""
        output = (
            "worktree /repo.git\n"
            "bare\n"
            "\n"
        )
        entries = _parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].is_bare is True

    def test_empty_output(self):
        """Empty output produces no entries."""
        entries = _parse_worktree_list("")
        assert entries == []

    def test_no_trailing_newline(self):
        """Handles output without trailing blank line."""
        output = (
            "worktree /repo\n"
            "HEAD aaa\n"
            "branch refs/heads/main"
        )
        entries = _parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].branch == "main"

    def test_strips_refs_heads_prefix(self):
        """Branch names have refs/heads/ prefix stripped."""
        output = (
            "worktree /repo\n"
            "HEAD aaa\n"
            "branch refs/heads/feature/specs\n"
            "\n"
        )
        entries = _parse_worktree_list(output)
        assert entries[0].branch == "feature/specs"


# ============================================================================
# discover_spec_worktree
# ============================================================================


class TestDiscoverSpecWorktree:
    """Test discover_spec_worktree() function."""

    def _make_config(
        self,
        branch_name: str = "kitty-specs",
        worktree_path: str = "kitty-specs",
    ) -> SpecStorageConfig:
        return SpecStorageConfig(
            branch_name=branch_name,
            worktree_path=worktree_path,
        )

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_healthy_worktree(self, mock_run, tmp_path: Path):
        """Registered worktree at expected path with correct branch -> healthy."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()
        # Create .git file to simulate worktree
        (wt_dir / ".git").write_text("gitdir: /repo/.git/worktrees/kitty-specs")

        resolved = str(wt_dir.resolve())

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/kitty-specs\n"
                    "\n",
                )
            if "status" in cmd_str and "--porcelain" in cmd_str:
                return _mock_run(0, "")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_HEALTHY
        assert state.registered is True
        assert state.branch_name == "kitty-specs"
        assert state.is_clean is True

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_missing_path(self, mock_run, tmp_path: Path):
        """Registered in git but directory doesn't exist -> missing_path."""
        resolved = str((tmp_path / "kitty-specs").resolve())

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/kitty-specs\n"
                    "\n",
                )
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_MISSING_PATH
        assert state.registered is True

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_wrong_branch(self, mock_run, tmp_path: Path):
        """Worktree at path but with different branch -> wrong_branch."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()
        (wt_dir / ".git").write_text("gitdir: /repo/.git/worktrees/other")

        resolved = str(wt_dir.resolve())

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/other-branch\n"
                    "\n",
                )
            if "status" in cmd_str:
                return _mock_run(0, "")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_WRONG_BRANCH
        assert state.branch_name == "other-branch"

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_path_conflict(self, mock_run, tmp_path: Path):
        """Regular directory (not a worktree) at expected path -> path_conflict."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()
        # No .git file = regular directory

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                # No entries matching our path
                return _mock_run(
                    0,
                    "worktree /some/other/path\n"
                    "HEAD abc123\n"
                    "branch refs/heads/main\n"
                    "\n",
                )
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_PATH_CONFLICT
        assert state.registered is False

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_missing_registration_with_git_file(self, mock_run, tmp_path: Path):
        """Directory with .git file but not in worktree list -> missing_registration."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()
        (wt_dir / ".git").write_text("gitdir: /repo/.git/worktrees/stale")

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    "worktree /some/other/path\n"
                    "HEAD abc123\n"
                    "branch refs/heads/main\n"
                    "\n",
                )
            if "status" in cmd_str:
                return _mock_run(0, "")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_MISSING_REGISTRATION
        assert state.registered is False

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_missing_everything(self, mock_run, tmp_path: Path):
        """No directory, not registered -> missing_registration."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    "worktree /some/other/path\n"
                    "HEAD abc123\n"
                    "branch refs/heads/main\n"
                    "\n",
                )
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_MISSING_REGISTRATION

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_dirty_worktree(self, mock_run, tmp_path: Path):
        """Worktree with uncommitted changes reports is_clean=False."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()
        (wt_dir / ".git").write_text("gitdir: /repo/.git/worktrees/kitty-specs")

        resolved = str(wt_dir.resolve())

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/kitty-specs\n"
                    "\n",
                )
            if "status" in cmd_str and "--porcelain" in cmd_str:
                return _mock_run(0, " M file.txt\nA  new.txt\n")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_HEALTHY
        assert state.is_clean is False
        assert state.has_manual_changes is True

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_branch_at_different_path(self, mock_run, tmp_path: Path):
        """Branch checked out at a different path than expected -> healthy at that path."""
        other_path = tmp_path / "other-location"
        other_path.mkdir()
        (other_path / ".git").write_text("gitdir: /repo/.git/worktrees/kitty-specs")

        resolved_other = str(other_path.resolve())

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved_other}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/kitty-specs\n"
                    "\n",
                )
            if "status" in cmd_str:
                return _mock_run(0, "")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_HEALTHY
        assert state.path == resolved_other
        assert state.branch_name == "kitty-specs"

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_git_worktree_list_fails(self, mock_run, tmp_path: Path):
        """git worktree list failure produces missing_registration."""
        def side_effect(cmd, **kwargs):
            return _mock_run(128, "", "fatal: not a git repo")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, self._make_config())
        assert state.health_status == HEALTH_MISSING_REGISTRATION
        assert state.registered is False

    @patch("specify_cli.core.spec_worktree_discovery.subprocess.run")
    def test_custom_config_paths(self, mock_run, tmp_path: Path):
        """Works with custom branch_name and worktree_path."""
        wt_dir = tmp_path / "specs"
        wt_dir.mkdir()
        (wt_dir / ".git").write_text("gitdir: /repo/.git/worktrees/specs")

        resolved = str(wt_dir.resolve())
        config = SpecStorageConfig(
            branch_name="my-specs",
            worktree_path="specs",
        )

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "worktree" in cmd_str and "list" in cmd_str:
                return _mock_run(
                    0,
                    f"worktree {resolved}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/my-specs\n"
                    "\n",
                )
            if "status" in cmd_str:
                return _mock_run(0, "")
            return _mock_run(0, "")

        mock_run.side_effect = side_effect

        state = discover_spec_worktree(tmp_path, config)
        assert state.health_status == HEALTH_HEALTHY
        assert state.branch_name == "my-specs"
