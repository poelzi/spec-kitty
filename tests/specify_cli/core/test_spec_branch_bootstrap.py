"""Unit tests for spec branch bootstrap (WP02).

Tests cover:
- _create_orphan_branch() plumbing
- _create_worktree() logic
- bootstrap_spec_storage() orchestration
- Idempotent behaviour (re-run on healthy state)
- Error handling for path conflicts and wrong branches
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from specify_cli.core.spec_branch_bootstrap import (
    _create_orphan_branch,
    _create_worktree,
    bootstrap_spec_storage,
)
from specify_cli.core.git_ops import SpecBranchState
from specify_cli.core.spec_storage_config import SpecStorageConfig
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    HEALTH_PATH_CONFLICT,
    HEALTH_WRONG_BRANCH,
    SpecWorktreeState,
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


def _make_branch_state(
    *,
    branch_name: str = "kitty-specs",
    exists_local: bool = False,
    exists_remote: bool = False,
    is_orphan: bool = False,
    head_commit: str | None = None,
) -> SpecBranchState:
    return SpecBranchState(
        branch_name=branch_name,
        exists_local=exists_local,
        exists_remote=exists_remote,
        is_orphan=is_orphan,
        head_commit=head_commit,
    )


def _make_worktree_state(
    *,
    path: str = "/repo/kitty-specs",
    registered: bool = False,
    branch_name: str | None = None,
    is_clean: bool = True,
    has_manual_changes: bool = False,
    health_status: str = HEALTH_MISSING_REGISTRATION,
) -> SpecWorktreeState:
    return SpecWorktreeState(
        path=path,
        registered=registered,
        branch_name=branch_name,
        is_clean=is_clean,
        has_manual_changes=has_manual_changes,
        health_status=health_status,
    )


# ============================================================================
# _create_orphan_branch
# ============================================================================


class TestCreateOrphanBranch:
    """Test _create_orphan_branch() function."""

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_success(self, mock_run, tmp_path: Path):
        """Creates orphan branch via plumbing commands."""
        mock_run.side_effect = [
            _mock_run(0, "4b825dc642cb6eb9a060e54bf899d69f"),  # mktree
            _mock_run(0, "abc1234def5678"),  # commit-tree
            _mock_run(0, ""),  # update-ref
        ]

        result = _create_orphan_branch(tmp_path, "kitty-specs")
        assert result is True
        assert mock_run.call_count == 3

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_failure_on_mktree(self, mock_run, tmp_path: Path):
        """Handles mktree failure gracefully."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "git mktree")

        result = _create_orphan_branch(tmp_path, "kitty-specs")
        assert result is False

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_with_console_output(self, mock_run, tmp_path: Path):
        """Console output on success."""
        mock_run.side_effect = [
            _mock_run(0, "treehash"),
            _mock_run(0, "commithash"),
            _mock_run(0, ""),
        ]
        console = MagicMock()
        result = _create_orphan_branch(tmp_path, "kitty-specs", console=console)
        assert result is True
        console.print.assert_called_once()


# ============================================================================
# _create_worktree
# ============================================================================


class TestCreateWorktree:
    """Test _create_worktree() function."""

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_success(self, mock_run, tmp_path: Path):
        """Creates worktree at specified path."""
        wt_path = tmp_path / "kitty-specs"
        mock_run.return_value = _mock_run(0, "")

        result = _create_worktree(tmp_path, wt_path, "kitty-specs")
        assert result is True

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_failure(self, mock_run, tmp_path: Path):
        """Handles worktree creation failure."""
        from subprocess import CalledProcessError
        wt_path = tmp_path / "kitty-specs"
        mock_run.side_effect = CalledProcessError(128, "git worktree add")

        result = _create_worktree(tmp_path, wt_path, "kitty-specs")
        assert result is False

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    def test_creates_parent_directory(self, mock_run, tmp_path: Path):
        """Creates parent directory if it doesn't exist."""
        wt_path = tmp_path / "deep" / "nested" / "kitty-specs"
        mock_run.return_value = _mock_run(0, "")

        result = _create_worktree(tmp_path, wt_path, "kitty-specs")
        assert result is True
        assert wt_path.parent.exists()


# ============================================================================
# bootstrap_spec_storage
# ============================================================================


class TestBootstrapSpecStorage:
    """Test bootstrap_spec_storage() orchestration."""

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.save_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap._create_orphan_branch")
    @patch("specify_cli.core.spec_branch_bootstrap._create_worktree")
    def test_fresh_repo_creates_everything(
        self,
        mock_create_wt,
        mock_create_branch,
        mock_has_config,
        mock_save_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Fresh repo: creates orphan branch, worktree, saves config."""
        # No existing config
        mock_has_config.return_value = False

        # Branch doesn't exist
        mock_inspect.return_value = _make_branch_state(exists_local=False)

        # Branch creation succeeds
        mock_create_branch.return_value = True

        # Worktree doesn't exist (missing registration, no dir)
        mock_discover.return_value = _make_worktree_state(
            path=str((tmp_path / "kitty-specs").resolve()),
            health_status=HEALTH_MISSING_REGISTRATION,
        )

        # Worktree creation succeeds
        mock_create_wt.return_value = True

        console = MagicMock()
        result = bootstrap_spec_storage(tmp_path, console=console)

        assert result is True
        mock_create_branch.assert_called_once()
        mock_create_wt.assert_called_once()
        mock_save_config.assert_called_once()

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.save_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    def test_idempotent_on_healthy(
        self,
        mock_has_config,
        mock_save_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Rerun on healthy state does not recreate anything."""
        mock_has_config.return_value = True

        # Branch exists and is orphan
        mock_inspect.return_value = _make_branch_state(
            exists_local=True, is_orphan=True, head_commit="abc1234"
        )

        # Worktree is healthy
        mock_discover.return_value = _make_worktree_state(
            health_status=HEALTH_HEALTHY,
            registered=True,
            branch_name="kitty-specs",
        )

        # Need to patch load_spec_storage_config to return a valid config
        with patch(
            "specify_cli.core.spec_branch_bootstrap.load_spec_storage_config"
        ) as mock_load:
            mock_load.return_value = SpecStorageConfig()
            result = bootstrap_spec_storage(tmp_path)

        assert result is True
        mock_save_config.assert_called_once()

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    def test_path_conflict_fails_safely(
        self,
        mock_has_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Path conflict returns False with error message."""
        mock_has_config.return_value = False

        mock_inspect.return_value = _make_branch_state(
            exists_local=True, is_orphan=True, head_commit="abc1234"
        )

        mock_discover.return_value = _make_worktree_state(
            health_status=HEALTH_PATH_CONFLICT,
        )

        console = MagicMock()
        result = bootstrap_spec_storage(tmp_path, console=console)

        assert result is False
        # Should have printed an error about path conflict
        assert any(
            "regular directory" in str(c)
            for c in console.print.call_args_list
        )

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    def test_wrong_branch_fails_safely(
        self,
        mock_has_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Wrong branch at worktree path returns False."""
        mock_has_config.return_value = False

        mock_inspect.return_value = _make_branch_state(
            exists_local=True, is_orphan=True, head_commit="abc1234"
        )

        mock_discover.return_value = _make_worktree_state(
            health_status=HEALTH_WRONG_BRANCH,
            branch_name="other-branch",
        )

        console = MagicMock()
        result = bootstrap_spec_storage(tmp_path, console=console)

        assert result is False

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.save_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.load_spec_storage_config")
    def test_custom_config_honored(
        self,
        mock_load,
        mock_has_config,
        mock_save_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Custom branch/path from config are used."""
        mock_has_config.return_value = True
        custom_config = SpecStorageConfig(
            branch_name="my-specs",
            worktree_path="specs-dir",
            auto_push=True,
        )
        mock_load.return_value = custom_config

        mock_inspect.return_value = _make_branch_state(
            branch_name="my-specs",
            exists_local=True,
            is_orphan=True,
            head_commit="def5678",
        )

        mock_discover.return_value = _make_worktree_state(
            path=str((tmp_path / "specs-dir").resolve()),
            health_status=HEALTH_HEALTHY,
            registered=True,
            branch_name="my-specs",
        )

        result = bootstrap_spec_storage(tmp_path)
        assert result is True

        # Verify config was saved with custom values
        saved_config = mock_save_config.call_args[0][1]
        assert saved_config.branch_name == "my-specs"
        assert saved_config.worktree_path == "specs-dir"
        assert saved_config.auto_push is True

    @patch("specify_cli.core.spec_branch_bootstrap._create_orphan_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    def test_branch_creation_failure_returns_false(
        self,
        mock_has_config,
        mock_inspect,
        mock_create_branch,
        tmp_path: Path,
    ):
        """Returns False when orphan branch creation fails."""
        mock_has_config.return_value = False
        mock_inspect.return_value = _make_branch_state(exists_local=False)
        mock_create_branch.return_value = False

        result = bootstrap_spec_storage(tmp_path)
        assert result is False

    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.save_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    def test_existing_non_orphan_branch_continues(
        self,
        mock_has_config,
        mock_save_config,
        mock_inspect,
        mock_discover,
        tmp_path: Path,
    ):
        """Branch exists but isn't orphan - continues with warning."""
        mock_has_config.return_value = False

        mock_inspect.return_value = _make_branch_state(
            exists_local=True,
            is_orphan=False,
            head_commit="abc1234",
        )

        mock_discover.return_value = _make_worktree_state(
            health_status=HEALTH_HEALTHY,
            registered=True,
            branch_name="kitty-specs",
        )

        console = MagicMock()
        result = bootstrap_spec_storage(tmp_path, console=console)

        assert result is True
        # Should have warned about non-orphan
        assert any(
            "NOT orphan" in str(c)
            for c in console.print.call_args_list
        )

    @patch("specify_cli.core.spec_branch_bootstrap.subprocess.run")
    @patch("specify_cli.core.spec_branch_bootstrap.discover_spec_worktree")
    @patch("specify_cli.core.spec_branch_bootstrap.inspect_spec_branch")
    @patch("specify_cli.core.spec_branch_bootstrap.save_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap.has_spec_storage_config")
    @patch("specify_cli.core.spec_branch_bootstrap._create_worktree")
    def test_missing_path_reprovisioned(
        self,
        mock_create_wt,
        mock_has_config,
        mock_save_config,
        mock_inspect,
        mock_discover,
        mock_subprocess,
        tmp_path: Path,
    ):
        """Missing path (registered but dir gone) is re-created."""
        mock_has_config.return_value = False
        mock_inspect.return_value = _make_branch_state(
            exists_local=True, is_orphan=True, head_commit="abc1234"
        )
        mock_discover.return_value = _make_worktree_state(
            health_status=HEALTH_MISSING_PATH,
            registered=True,
            branch_name="kitty-specs",
        )
        mock_subprocess.return_value = _mock_run(0, "")  # git worktree prune
        mock_create_wt.return_value = True

        console = MagicMock()
        result = bootstrap_spec_storage(tmp_path, console=console)

        assert result is True
        mock_create_wt.assert_called_once()
