"""Unit tests for spec storage health check and repair (WP05 / T027).

Tests cover:
- T023: SpecStorageHealthReport and check_spec_storage_health()
  - Healthy topology pass-through
  - Not-configured (legacy) pass-through
  - Missing worktree detection
  - Missing registration detection
  - Path conflict detection
  - Wrong branch detection
  - Branch missing locally
- T024: repair_spec_storage()
  - Missing worktree auto-repair (prune + re-add)
  - Missing registration auto-repair
  - Refuses to repair conflicts
- T025: Path conflict handling
  - Reports conflict clearly
  - Suggests remediation
  - Never auto-deletes
- T026: ensure_spec_storage_ready() preflight
  - Returns path for healthy state
  - Returns legacy path for not-configured state
  - Attempts repair for repairable state
  - Returns None for conflicts
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

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
from specify_cli.core.spec_health import (
    STATUS_CONFLICT,
    STATUS_HEALTHY,
    STATUS_NOT_CONFIGURED,
    STATUS_REPAIRABLE,
    SpecStorageHealthReport,
    check_spec_storage_health,
    ensure_spec_storage_ready,
    repair_spec_storage,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_config(
    branch_name: str = "kitty-specs",
    worktree_path: str = "kitty-specs",
) -> SpecStorageConfig:
    return SpecStorageConfig(
        branch_name=branch_name,
        worktree_path=worktree_path,
    )


def _make_branch_state(
    branch_name: str = "kitty-specs",
    exists_local: bool = True,
    exists_remote: bool = False,
    is_orphan: bool = True,
    head_commit: str | None = "abc1234",
) -> SpecBranchState:
    return SpecBranchState(
        branch_name=branch_name,
        exists_local=exists_local,
        exists_remote=exists_remote,
        is_orphan=is_orphan,
        head_commit=head_commit,
    )


def _make_worktree_state(
    path: str = "/repo/kitty-specs",
    registered: bool = True,
    branch_name: str | None = "kitty-specs",
    is_clean: bool = True,
    has_manual_changes: bool = False,
    health_status: str = HEALTH_HEALTHY,
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
# T023 - check_spec_storage_health
# ============================================================================


class TestCheckSpecStorageHealth:
    """Tests for check_spec_storage_health() function."""

    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_healthy_topology(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        tmp_path: Path,
    ):
        """Healthy topology passes through with no issues."""
        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            path=str(tmp_path / "kitty-specs"),
            health_status=HEALTH_HEALTHY,
        )

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_HEALTHY
        assert report.config_present is True
        assert report.branch_state is not None
        assert report.worktree_state is not None
        assert report.issues == []
        assert report.repairs_available == []

    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_not_configured(self, mock_has_config, tmp_path: Path):
        """Not configured (legacy) project returns not_configured status."""
        mock_has_config.return_value = False

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_NOT_CONFIGURED
        assert report.config_present is False
        assert report.branch_state is None
        assert report.worktree_state is None
        assert len(report.issues) == 1
        assert "No spec_storage configuration" in report.issues[0]

    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_missing_worktree_path(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        tmp_path: Path,
    ):
        """Missing worktree directory -> repairable."""
        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            health_status=HEALTH_MISSING_PATH,
        )

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_REPAIRABLE
        assert len(report.issues) > 0
        assert len(report.repairs_available) > 0
        assert "registered" in report.issues[0].lower() or "missing" in report.issues[0].lower()

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_missing_registration_dir_exists(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        mock_get_abs_path,
        tmp_path: Path,
    ):
        """Directory exists but not registered -> repairable."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()

        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_MISSING_REGISTRATION,
        )
        mock_get_abs_path.return_value = wt_dir

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_REPAIRABLE
        assert any("not registered" in i.lower() for i in report.issues)
        assert len(report.repairs_available) > 0

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_missing_registration_dir_missing(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        mock_get_abs_path,
        tmp_path: Path,
    ):
        """No directory and not registered -> repairable (create from branch)."""
        wt_dir = tmp_path / "kitty-specs"
        # Don't create the directory

        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_MISSING_REGISTRATION,
        )
        mock_get_abs_path.return_value = wt_dir

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_REPAIRABLE
        assert any("does not exist" in i.lower() for i in report.issues)
        assert any("create worktree" in r.lower() for r in report.repairs_available)

    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_wrong_branch(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        tmp_path: Path,
    ):
        """Worktree pointing to wrong branch -> conflict."""
        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            branch_name="other-branch",
            health_status=HEALTH_WRONG_BRANCH,
        )

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_CONFLICT
        assert any("other-branch" in i for i in report.issues)
        assert report.repairs_available == []

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_path_conflict(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        mock_get_abs_path,
        tmp_path: Path,
    ):
        """Regular directory at worktree path -> conflict with remediation guidance."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()

        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_PATH_CONFLICT,
        )
        mock_get_abs_path.return_value = wt_dir

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_CONFLICT
        assert any("regular directory" in i.lower() for i in report.issues)
        assert any("rename" in i.lower() or "move" in i.lower() for i in report.issues)
        assert report.repairs_available == []

    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_branch_missing_locally_with_remote(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        tmp_path: Path,
    ):
        """Branch missing locally but exists on remote -> repairable."""
        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state(
            exists_local=False,
            exists_remote=True,
            is_orphan=False,
            head_commit=None,
        )
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_MISSING_REGISTRATION,
        )

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_REPAIRABLE
        assert any("does not exist locally" in i.lower() for i in report.issues)
        assert any("fetch" in r.lower() for r in report.repairs_available)

    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_branch_missing_locally_no_remote(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        tmp_path: Path,
    ):
        """Branch missing locally and no remote -> conflict."""
        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state(
            exists_local=False,
            exists_remote=False,
            is_orphan=False,
            head_commit=None,
        )
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_MISSING_REGISTRATION,
        )

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_CONFLICT
        assert any("does not exist locally" in i.lower() for i in report.issues)


# ============================================================================
# T024 - repair_spec_storage
# ============================================================================


class TestRepairSpecStorage:
    """Tests for repair_spec_storage() function."""

    def test_refuses_non_repairable_status(self, tmp_path: Path):
        """Does not attempt repair for non-repairable states."""
        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_PATH_CONFLICT),
            health_status=STATUS_CONFLICT,
            issues=["Path conflict"],
            repairs_available=[],
        )

        result = repair_spec_storage(tmp_path, report)
        assert result is False

    def test_refuses_healthy_status(self, tmp_path: Path):
        """Does not attempt repair for healthy states."""
        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_HEALTHY),
            health_status=STATUS_HEALTHY,
            issues=[],
            repairs_available=[],
        )

        result = repair_spec_storage(tmp_path, report)
        assert result is False

    def test_refuses_not_configured(self, tmp_path: Path):
        """Does not attempt repair for not-configured states."""
        report = SpecStorageHealthReport(
            config_present=False,
            branch_state=None,
            worktree_state=None,
            health_status=STATUS_NOT_CONFIGURED,
            issues=["Not configured"],
            repairs_available=[],
        )

        result = repair_spec_storage(tmp_path, report)
        assert result is False

    @patch("specify_cli.core.spec_health._prune_and_readd_worktree")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    def test_repairs_missing_path(
        self,
        mock_load_config,
        mock_prune_readd,
        tmp_path: Path,
    ):
        """Missing worktree path triggers prune + re-add."""
        mock_load_config.return_value = _make_config()
        mock_prune_readd.return_value = True

        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_MISSING_PATH),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing worktree path"],
            repairs_available=["Prune and re-add"],
        )

        result = repair_spec_storage(tmp_path, report)

        assert result is True
        mock_prune_readd.assert_called_once_with(tmp_path, mock_load_config.return_value)

    @patch("specify_cli.core.spec_health._repair_missing_registration")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    def test_repairs_missing_registration(
        self,
        mock_load_config,
        mock_repair_reg,
        tmp_path: Path,
    ):
        """Missing registration triggers re-registration repair."""
        mock_load_config.return_value = _make_config()
        mock_repair_reg.return_value = True

        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(
                registered=False,
                branch_name=None,
                health_status=HEALTH_MISSING_REGISTRATION,
            ),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing registration"],
            repairs_available=["Re-register worktree"],
        )

        result = repair_spec_storage(tmp_path, report)

        assert result is True
        mock_repair_reg.assert_called_once_with(tmp_path, mock_load_config.return_value)

    @patch("specify_cli.core.spec_health._run_git")
    @patch("specify_cli.core.spec_health._fetch_remote_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    def test_repairs_branch_from_remote(
        self,
        mock_load_config,
        mock_fetch,
        mock_run_git,
        tmp_path: Path,
    ):
        """Missing local branch with remote triggers fetch."""
        mock_load_config.return_value = _make_config()
        mock_fetch.return_value = True
        mock_run_git.return_value = MagicMock(returncode=0)

        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(
                exists_local=False,
                exists_remote=True,
                head_commit=None,
            ),
            worktree_state=_make_worktree_state(
                registered=False,
                branch_name=None,
                health_status=HEALTH_MISSING_REGISTRATION,
            ),
            health_status=STATUS_REPAIRABLE,
            issues=["Branch missing locally"],
            repairs_available=["Fetch from remote"],
        )

        result = repair_spec_storage(tmp_path, report)

        assert result is True
        mock_fetch.assert_called_once_with(tmp_path, "kitty-specs")

    @patch("specify_cli.core.spec_health._prune_and_readd_worktree")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    def test_repair_failure_returns_false(
        self,
        mock_load_config,
        mock_prune_readd,
        tmp_path: Path,
    ):
        """Failed repair returns False."""
        mock_load_config.return_value = _make_config()
        mock_prune_readd.return_value = False

        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_MISSING_PATH),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing worktree path"],
            repairs_available=["Prune and re-add"],
        )

        result = repair_spec_storage(tmp_path, report)
        assert result is False


# ============================================================================
# T025 - Path conflict handling
# ============================================================================


class TestPathConflictHandling:
    """Tests for safe path-conflict handling."""

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_conflict_reports_clearly(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        mock_get_abs_path,
        tmp_path: Path,
    ):
        """Path conflict is reported with clear description."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()

        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_PATH_CONFLICT,
        )
        mock_get_abs_path.return_value = wt_dir

        report = check_spec_storage_health(tmp_path)

        assert report.health_status == STATUS_CONFLICT
        # Should mention it's a regular directory
        assert any("regular directory" in i.lower() for i in report.issues)
        # Should suggest remediation
        assert any("rename" in i.lower() or "move" in i.lower() for i in report.issues)

    def test_conflict_never_auto_repaired(self, tmp_path: Path):
        """Conflict states are never auto-repaired."""
        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_PATH_CONFLICT),
            health_status=STATUS_CONFLICT,
            issues=["Path conflict"],
            repairs_available=[],
        )

        result = repair_spec_storage(tmp_path, report)
        assert result is False

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.discover_spec_worktree")
    @patch("specify_cli.core.spec_health.inspect_spec_branch")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.has_spec_storage_config")
    def test_conflict_has_no_repairs_available(
        self,
        mock_has_config,
        mock_load_config,
        mock_inspect_branch,
        mock_discover_wt,
        mock_get_abs_path,
        tmp_path: Path,
    ):
        """Path conflict has empty repairs_available list."""
        wt_dir = tmp_path / "kitty-specs"
        wt_dir.mkdir()

        mock_has_config.return_value = True
        mock_load_config.return_value = _make_config()
        mock_inspect_branch.return_value = _make_branch_state()
        mock_discover_wt.return_value = _make_worktree_state(
            registered=False,
            branch_name=None,
            health_status=HEALTH_PATH_CONFLICT,
        )
        mock_get_abs_path.return_value = wt_dir

        report = check_spec_storage_health(tmp_path)
        assert report.repairs_available == []


# ============================================================================
# T026 - ensure_spec_storage_ready (preflight)
# ============================================================================


class TestEnsureSpecStorageReady:
    """Tests for ensure_spec_storage_ready() preflight function."""

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_returns_path_for_healthy(
        self,
        mock_check,
        mock_load_config,
        mock_get_abs,
        tmp_path: Path,
    ):
        """Healthy state returns the worktree path immediately."""
        expected_path = tmp_path / "kitty-specs"
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_HEALTHY),
            health_status=STATUS_HEALTHY,
        )
        mock_load_config.return_value = _make_config()
        mock_get_abs.return_value = expected_path

        result = ensure_spec_storage_ready(tmp_path)
        assert result == expected_path

    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_returns_legacy_path_for_not_configured(
        self,
        mock_check,
        tmp_path: Path,
    ):
        """Not-configured returns legacy kitty-specs/ if it exists."""
        legacy_dir = tmp_path / "kitty-specs"
        legacy_dir.mkdir()

        mock_check.return_value = SpecStorageHealthReport(
            config_present=False,
            branch_state=None,
            worktree_state=None,
            health_status=STATUS_NOT_CONFIGURED,
        )

        result = ensure_spec_storage_ready(tmp_path)
        assert result == legacy_dir

    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_returns_none_for_not_configured_no_dir(
        self,
        mock_check,
        tmp_path: Path,
    ):
        """Not-configured with no kitty-specs/ dir returns None."""
        mock_check.return_value = SpecStorageHealthReport(
            config_present=False,
            branch_state=None,
            worktree_state=None,
            health_status=STATUS_NOT_CONFIGURED,
        )

        result = ensure_spec_storage_ready(tmp_path)
        assert result is None

    @patch("specify_cli.core.spec_health.get_spec_worktree_abs_path")
    @patch("specify_cli.core.spec_health.load_spec_storage_config")
    @patch("specify_cli.core.spec_health.repair_spec_storage")
    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_attempts_repair_for_repairable(
        self,
        mock_check,
        mock_repair,
        mock_load_config,
        mock_get_abs,
        tmp_path: Path,
    ):
        """Repairable state triggers repair and returns path on success."""
        expected_path = tmp_path / "kitty-specs"
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_MISSING_PATH),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing worktree path"],
            repairs_available=["Prune and re-add"],
        )
        mock_repair.return_value = True
        mock_load_config.return_value = _make_config()
        mock_get_abs.return_value = expected_path

        result = ensure_spec_storage_ready(tmp_path)

        assert result == expected_path
        mock_repair.assert_called_once()

    @patch("specify_cli.core.spec_health.repair_spec_storage")
    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_returns_none_for_failed_repair(
        self,
        mock_check,
        mock_repair,
        tmp_path: Path,
    ):
        """Failed repair returns None."""
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_MISSING_PATH),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing worktree path"],
            repairs_available=["Prune and re-add"],
        )
        mock_repair.return_value = False

        result = ensure_spec_storage_ready(tmp_path)
        assert result is None

    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_returns_none_for_conflict(
        self,
        mock_check,
        tmp_path: Path,
    ):
        """Conflict state returns None."""
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_PATH_CONFLICT),
            health_status=STATUS_CONFLICT,
            issues=["Path conflict"],
            repairs_available=[],
        )

        result = ensure_spec_storage_ready(tmp_path)
        assert result is None

    @patch("specify_cli.core.spec_health.repair_spec_storage")
    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_prints_repair_messages_with_console(
        self,
        mock_check,
        mock_repair,
        tmp_path: Path,
    ):
        """When console is provided, prints repair status messages."""
        mock_console = MagicMock()
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_MISSING_PATH),
            health_status=STATUS_REPAIRABLE,
            issues=["Missing worktree path"],
            repairs_available=["Prune and re-add"],
        )
        mock_repair.return_value = False

        ensure_spec_storage_ready(tmp_path, console=mock_console)

        # Should have printed at least the attempt and failure messages
        assert mock_console.print.call_count >= 2

    @patch("specify_cli.core.spec_health.check_spec_storage_health")
    def test_prints_conflict_messages_with_console(
        self,
        mock_check,
        tmp_path: Path,
    ):
        """When console is provided, prints conflict messages."""
        mock_console = MagicMock()
        mock_check.return_value = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(health_status=HEALTH_PATH_CONFLICT),
            health_status=STATUS_CONFLICT,
            issues=["Path conflict at kitty-specs/"],
            repairs_available=[],
        )

        ensure_spec_storage_ready(tmp_path, console=mock_console)

        # Should print conflict header + each issue
        assert mock_console.print.call_count >= 2


# ============================================================================
# Status constants
# ============================================================================


class TestStatusConstants:
    """Test status constants are the expected values."""

    def test_healthy(self):
        assert STATUS_HEALTHY == "healthy"

    def test_repairable(self):
        assert STATUS_REPAIRABLE == "repairable"

    def test_conflict(self):
        assert STATUS_CONFLICT == "conflict"

    def test_not_configured(self):
        assert STATUS_NOT_CONFIGURED == "not_configured"


# ============================================================================
# SpecStorageHealthReport dataclass
# ============================================================================


class TestSpecStorageHealthReport:
    """Test SpecStorageHealthReport dataclass."""

    def test_defaults(self):
        """Default values for issues and repairs_available."""
        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=None,
            worktree_state=None,
            health_status=STATUS_HEALTHY,
        )
        assert report.issues == []
        assert report.repairs_available == []

    def test_with_issues(self):
        """Can be created with issues and repairs."""
        report = SpecStorageHealthReport(
            config_present=True,
            branch_state=_make_branch_state(),
            worktree_state=_make_worktree_state(),
            health_status=STATUS_REPAIRABLE,
            issues=["Problem 1", "Problem 2"],
            repairs_available=["Fix 1"],
        )
        assert len(report.issues) == 2
        assert len(report.repairs_available) == 1
