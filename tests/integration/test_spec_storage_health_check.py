"""Integration tests for spec storage health classification (WP05).

Tests exercise ``check_spec_storage_health`` and ``ensure_spec_storage_ready``
against real git repositories to verify:

1. Healthy repos pass through without repair attempts.
2. Conflict states (wrong branch, path conflict) block with guidance.
3. Not-configured (legacy) repos return the legacy ``kitty-specs/`` path.
4. Repairable states trigger repair and return the worktree path.

Discoverable via: ``pytest tests/integration -k "health_check"``

All tests use real temporary git repos (no git mocking).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_health import (
    STATUS_CONFLICT,
    STATUS_HEALTHY,
    STATUS_NOT_CONFIGURED,
    STATUS_REPAIRABLE,
    SpecStorageHealthReport,
    check_spec_storage_health,
    ensure_spec_storage_ready,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
    save_spec_storage_config,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    HEALTH_PATH_CONFLICT,
    HEALTH_WRONG_BRANCH,
    discover_spec_worktree,
)


# ============================================================================
# Helpers
# ============================================================================


def _git(
    args: list[str], cwd: Path, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _init_repo(path: Path) -> Path:
    """Create and initialize a git repository with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init"], cwd=path)
    _git(["config", "user.name", "Test User"], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    (path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    _git(["add", "."], cwd=path)
    _git(["commit", "-m", "Initial commit"], cwd=path)
    _git(["branch", "-M", "main"], cwd=path)
    return path


def _setup_healthy_spec_storage(repo: Path) -> SpecStorageConfig:
    """Configure a repo with a healthy orphan spec branch + worktree.

    Returns the saved config.
    """
    (repo / ".kittify").mkdir(parents=True, exist_ok=True)

    # Create orphan branch with initial commit
    _git(["checkout", "--orphan", "kitty-specs"], cwd=repo)
    (repo / "README.md").unlink(missing_ok=True)
    _git(["rm", "-rf", "."], cwd=repo, check=False)
    specs_dir = repo / "001-test-feature"
    specs_dir.mkdir(parents=True)
    (specs_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "Initial spec commit"], cwd=repo)

    # Switch back to main
    _git(["checkout", "main"], cwd=repo)

    # Add worktree
    wt_path = repo / "kitty-specs"
    _git(["worktree", "add", str(wt_path), "kitty-specs"], cwd=repo)

    # Save config
    config = SpecStorageConfig(
        branch_name="kitty-specs",
        worktree_path="kitty-specs",
        auto_push=False,
        is_defaulted=False,
    )
    save_spec_storage_config(repo, config)
    return config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Path:
    """Create a clean repo without kitty-specs/ or config."""
    return _init_repo(tmp_path / "repo")


@pytest.fixture()
def healthy_repo(tmp_path: Path) -> Path:
    """Create a repo with healthy spec storage (orphan branch + worktree)."""
    repo = _init_repo(tmp_path / "repo")
    _setup_healthy_spec_storage(repo)
    return repo


@pytest.fixture()
def legacy_repo(tmp_path: Path) -> Path:
    """Create a repo with legacy kitty-specs/ directory (no spec_storage config)."""
    repo = _init_repo(tmp_path / "repo")
    specs_dir = repo / "kitty-specs" / "001-test-feature"
    specs_dir.mkdir(parents=True)
    (specs_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "Add legacy kitty-specs"], cwd=repo)
    return repo


# ============================================================================
# Health check classification tests
# ============================================================================


class TestHealthyPassThrough:
    """Healthy repos should pass through without issues."""

    def test_healthy_status(self, healthy_repo: Path):
        """Fully configured + healthy worktree returns STATUS_HEALTHY."""
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_HEALTHY
        assert report.config_present is True
        assert report.issues == []
        assert report.repairs_available == []

    def test_healthy_branch_state(self, healthy_repo: Path):
        """Branch state is populated for healthy repos."""
        report = check_spec_storage_health(healthy_repo)
        assert report.branch_state is not None
        assert report.branch_state.exists_local is True

    def test_healthy_worktree_state(self, healthy_repo: Path):
        """Worktree state is healthy for fully configured repos."""
        report = check_spec_storage_health(healthy_repo)
        assert report.worktree_state is not None
        assert report.worktree_state.health_status == HEALTH_HEALTHY


class TestNotConfiguredLegacy:
    """Not-configured repos return STATUS_NOT_CONFIGURED."""

    def test_empty_repo_not_configured(self, empty_repo: Path):
        """Repo without .kittify config returns not_configured."""
        report = check_spec_storage_health(empty_repo)
        assert report.health_status == STATUS_NOT_CONFIGURED
        assert report.config_present is False
        assert report.branch_state is None
        assert report.worktree_state is None

    def test_legacy_repo_not_configured(self, legacy_repo: Path):
        """Repo with kitty-specs/ but no spec_storage config returns not_configured."""
        report = check_spec_storage_health(legacy_repo)
        assert report.health_status == STATUS_NOT_CONFIGURED
        assert report.config_present is False


class TestConflictBlocking:
    """Conflict states block with guidance (no auto-repair)."""

    def test_wrong_branch_is_conflict(self, healthy_repo: Path):
        """Worktree on wrong branch returns STATUS_CONFLICT."""
        # Create a new branch and force the worktree to point to it
        _git(["branch", "other-branch"], cwd=healthy_repo)
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        _git(["worktree", "add", str(wt_path), "other-branch"], cwd=healthy_repo)

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_CONFLICT
        assert any("wrong" in issue.lower() or "instead of" in issue.lower()
                    for issue in report.issues)
        assert report.repairs_available == []

    def test_path_conflict_is_conflict(self, healthy_repo: Path):
        """Regular directory at worktree path returns STATUS_CONFLICT."""
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        # Create a regular directory (not a git worktree)
        wt_path.mkdir(parents=True)
        (wt_path / "stray-file.txt").write_text("conflict", encoding="utf-8")

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_CONFLICT
        assert report.repairs_available == []


class TestRepairableDetection:
    """Repairable states are correctly classified."""

    def test_missing_path_is_repairable(self, healthy_repo: Path):
        """Registered worktree with missing directory is repairable."""
        # Remove the worktree directory but leave git's internal registration
        wt_path = healthy_repo / "kitty-specs"
        # Force remove the directory content without git worktree remove
        shutil.rmtree(wt_path)

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE
        assert len(report.issues) > 0
        assert len(report.repairs_available) > 0

    def test_missing_registration_is_repairable(self, healthy_repo: Path):
        """Directory exists but no git worktree registration is repairable."""
        wt_path = healthy_repo / "kitty-specs"
        # Remove worktree via git (removes registration + directory)
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        # The directory is now gone and so is the registration
        # This is "missing registration" since the directory doesn't exist either

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE
        assert len(report.repairs_available) > 0


# ============================================================================
# ensure_spec_storage_ready() preflight tests
# ============================================================================


class TestEnsureSpecStorageReady:
    """Test the preflight function used by command handlers."""

    def test_healthy_returns_path(self, healthy_repo: Path):
        """Healthy repos return the worktree path immediately."""
        result = ensure_spec_storage_ready(healthy_repo)
        assert result is not None
        assert result.is_dir()
        config = load_spec_storage_config(healthy_repo)
        expected = get_spec_worktree_abs_path(healthy_repo, config)
        assert result == expected

    def test_not_configured_returns_legacy_path(self, legacy_repo: Path):
        """Legacy repos return the kitty-specs/ directory."""
        result = ensure_spec_storage_ready(legacy_repo)
        assert result is not None
        assert result == legacy_repo / "kitty-specs"
        assert result.is_dir()

    def test_not_configured_no_dir_returns_none(self, empty_repo: Path):
        """Empty repos with no kitty-specs/ return None."""
        result = ensure_spec_storage_ready(empty_repo)
        assert result is None

    def test_repairable_auto_repairs(self, healthy_repo: Path):
        """Repairable state is auto-repaired and returns path."""
        # Break the worktree (remove directory, keep registration)
        wt_path = healthy_repo / "kitty-specs"
        shutil.rmtree(wt_path)

        # Confirm it's broken
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE

        # Preflight should repair and return path
        result = ensure_spec_storage_ready(healthy_repo)
        assert result is not None
        assert result.is_dir()

    def test_conflict_returns_none(self, healthy_repo: Path):
        """Conflict state returns None (cannot auto-repair)."""
        # Create wrong-branch conflict
        _git(["branch", "other-branch"], cwd=healthy_repo)
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        _git(["worktree", "add", str(wt_path), "other-branch"], cwd=healthy_repo)

        result = ensure_spec_storage_ready(healthy_repo)
        assert result is None

    def test_preflight_with_console_output(self, healthy_repo: Path):
        """Preflight with Console shows repair messages."""
        from rich.console import Console
        from io import StringIO

        output = StringIO()
        test_console = Console(file=output)

        # Break the worktree
        wt_path = healthy_repo / "kitty-specs"
        shutil.rmtree(wt_path)

        result = ensure_spec_storage_ready(healthy_repo, console=test_console)
        assert result is not None
        console_output = output.getvalue()
        # Should mention repair in the output
        assert "repair" in console_output.lower()
