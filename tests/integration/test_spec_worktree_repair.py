"""Integration tests for spec storage auto-repair flows (WP05).

Tests exercise ``repair_spec_storage`` against real git repositories to
verify auto-repair for safe failure states:

1. Missing worktree path (registered but directory gone) -> prune + re-add.
2. Missing registration (directory gone, registration gone) -> add worktree.
3. Clone bootstrap (branch exists on remote but not locally) -> fetch + add.
4. Conflict states are never auto-repaired.

Discoverable via: ``pytest tests/integration -k "worktree_repair"``

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
    check_spec_storage_health,
    ensure_spec_storage_ready,
    repair_spec_storage,
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
    """Configure a repo with a healthy orphan spec branch + worktree."""
    (repo / ".kittify").mkdir(parents=True, exist_ok=True)

    # Create orphan branch with initial content
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


def _create_bare_remote(tmp_path: Path, source_repo: Path) -> Path:
    """Create a bare remote clone from source_repo."""
    bare_path = tmp_path / "remote.git"
    _git(["clone", "--bare", str(source_repo), str(bare_path)], cwd=tmp_path)
    return bare_path


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def healthy_repo(tmp_path: Path) -> Path:
    """Create a repo with healthy spec storage."""
    repo = _init_repo(tmp_path / "repo")
    _setup_healthy_spec_storage(repo)
    return repo


# ============================================================================
# Missing path repair (worktree registered, directory gone)
# ============================================================================


class TestMissingPathRepair:
    """Repair flows for registered worktree with missing directory."""

    def test_repair_recreates_worktree(self, healthy_repo: Path):
        """Removing worktree dir triggers prune+re-add repair."""
        wt_path = healthy_repo / "kitty-specs"
        # Destroy the directory without telling git
        shutil.rmtree(wt_path)

        # Confirm broken
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE

        # Repair
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        # Verify healthy after repair
        report_after = check_spec_storage_health(healthy_repo)
        assert report_after.health_status == STATUS_HEALTHY

    def test_repaired_worktree_has_content(self, healthy_repo: Path):
        """Repaired worktree retains the spec branch content."""
        wt_path = healthy_repo / "kitty-specs"
        shutil.rmtree(wt_path)

        report = check_spec_storage_health(healthy_repo)
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        # Content from the orphan branch should be present
        assert (wt_path / "001-test-feature" / "spec.md").exists()

    def test_ensure_ready_auto_repairs_missing_path(self, healthy_repo: Path):
        """ensure_spec_storage_ready auto-repairs and returns path."""
        wt_path = healthy_repo / "kitty-specs"
        shutil.rmtree(wt_path)

        result = ensure_spec_storage_ready(healthy_repo)
        assert result is not None
        assert result.is_dir()
        assert (result / "001-test-feature" / "spec.md").exists()


# ============================================================================
# Missing registration repair (no git worktree entry)
# ============================================================================


class TestMissingRegistrationRepair:
    """Repair flows for missing worktree registration."""

    def test_repair_adds_worktree(self, healthy_repo: Path):
        """When both registration and directory are gone, repair re-adds worktree."""
        wt_path = healthy_repo / "kitty-specs"
        # Remove via git (removes both registration and directory)
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)

        # Confirm broken
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE

        # Repair
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        # Verify healthy after repair
        report_after = check_spec_storage_health(healthy_repo)
        assert report_after.health_status == STATUS_HEALTHY

    def test_repaired_registration_has_content(self, healthy_repo: Path):
        """Repaired worktree contains spec content."""
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)

        report = check_spec_storage_health(healthy_repo)
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        assert (wt_path / "001-test-feature" / "spec.md").exists()


# ============================================================================
# Clone bootstrap (branch on remote, not local)
# ============================================================================


class TestCloneBootstrapRepair:
    """Repair flows for branch available on remote but not locally."""

    def test_fetch_and_setup_from_remote(self, tmp_path: Path):
        """Branch on remote can be fetched and worktree set up."""
        # Create source repo with healthy spec storage
        source = _init_repo(tmp_path / "source")
        _setup_healthy_spec_storage(source)

        # Create a bare remote from the source
        bare = _create_bare_remote(tmp_path, source)

        # Clone from bare (will have kitty-specs branch on remote)
        clone_path = tmp_path / "clone"
        _git(["clone", str(bare), str(clone_path)], cwd=tmp_path)
        _git(["config", "user.name", "Test User"], cwd=clone_path)
        _git(["config", "user.email", "test@example.com"], cwd=clone_path)

        # Set up .kittify config pointing at branch that exists on remote
        (clone_path / ".kittify").mkdir(parents=True, exist_ok=True)
        config = SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="kitty-specs",
            auto_push=False,
            is_defaulted=False,
        )
        save_spec_storage_config(clone_path, config)

        # Delete local branch if it was auto-created
        _git(["branch", "-D", "kitty-specs"], cwd=clone_path, check=False)

        # Confirm it's repairable (branch on remote, not local)
        report = check_spec_storage_health(clone_path)
        assert report.health_status == STATUS_REPAIRABLE

        # Repair should fetch from remote and set up worktree
        success = repair_spec_storage(clone_path, report)
        assert success is True

        # Verify healthy
        report_after = check_spec_storage_health(clone_path)
        assert report_after.health_status == STATUS_HEALTHY


# ============================================================================
# Conflict states are NOT repaired
# ============================================================================


class TestConflictNotRepaired:
    """Conflict states must not be auto-repaired."""

    def test_wrong_branch_not_repaired(self, healthy_repo: Path):
        """Wrong branch conflict returns False from repair."""
        _git(["branch", "other-branch"], cwd=healthy_repo)
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        _git(["worktree", "add", str(wt_path), "other-branch"], cwd=healthy_repo)

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_CONFLICT

        success = repair_spec_storage(healthy_repo, report)
        assert success is False

    def test_path_conflict_not_repaired(self, healthy_repo: Path):
        """Regular directory at worktree path returns False from repair."""
        wt_path = healthy_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        wt_path.mkdir(parents=True)
        (wt_path / "stray-file.txt").write_text("conflict", encoding="utf-8")

        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_CONFLICT

        success = repair_spec_storage(healthy_repo, report)
        assert success is False

    def test_not_configured_not_repaired(self, tmp_path: Path):
        """Not-configured repos return False from repair."""
        repo = _init_repo(tmp_path / "repo")
        report = check_spec_storage_health(repo)
        assert report.health_status == STATUS_NOT_CONFIGURED

        success = repair_spec_storage(repo, report)
        assert success is False


# ============================================================================
# End-to-end: repair + verify healthy
# ============================================================================


class TestRepairEndToEnd:
    """Full round-trip: break -> check -> repair -> verify healthy."""

    def test_full_cycle_missing_path(self, healthy_repo: Path):
        """Break path -> repair -> verify all green."""
        wt_path = healthy_repo / "kitty-specs"

        # 1. Verify initially healthy
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_HEALTHY

        # 2. Break it
        shutil.rmtree(wt_path)
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE

        # 3. Repair
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        # 4. Verify healthy again
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_HEALTHY

        # 5. Content accessible
        config = load_spec_storage_config(healthy_repo)
        state = discover_spec_worktree(healthy_repo, config)
        assert state.health_status == HEALTH_HEALTHY

    def test_full_cycle_missing_registration(self, healthy_repo: Path):
        """Break registration -> repair -> verify all green."""
        wt_path = healthy_repo / "kitty-specs"

        # 1. Verify initially healthy
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_HEALTHY

        # 2. Break it (remove both registration and directory)
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=healthy_repo)
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_REPAIRABLE

        # 3. Repair
        success = repair_spec_storage(healthy_repo, report)
        assert success is True

        # 4. Verify healthy again
        report = check_spec_storage_health(healthy_repo)
        assert report.health_status == STATUS_HEALTHY

        # 5. Content accessible
        assert (wt_path / "001-test-feature" / "spec.md").exists()
