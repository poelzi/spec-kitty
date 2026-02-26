"""Integration tests for the spec branch worktree migration (WP04).

These tests exercise the migration through the upgrade runner path and
validate the review-feedback fixes:

1. ``_classify()`` validates worktree health for already-migrated detection.
2. ``detect()``/``apply()`` round-trips through the upgrade runner surface
   the explicit ``already_migrated`` no-op result.
3. Tests are discoverable via ``pytest tests/integration -k "spec_storage_migration"``.

All tests use real temporary git repos (no git mocking).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_storage_config import (
    has_spec_storage_config,
    load_spec_storage_config,
    save_spec_storage_config,
    SpecStorageConfig,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    discover_spec_worktree,
)
from specify_cli.upgrade.migrations.m_0_16_0_spec_branch_worktree import (
    STATUS_ALREADY_MIGRATED,
    STATUS_NOT_APPLICABLE,
    STATUS_SUCCESS,
    SpecBranchWorktreeMigration,
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


def _create_legacy_layout(repo: Path) -> None:
    """Create a legacy kitty-specs/ directory tracked on the planning branch."""
    kittify = repo / ".kittify"
    kittify.mkdir(parents=True, exist_ok=True)

    specs_dir = repo / "kitty-specs"
    feature_dir = specs_dir / "001-test-feature"
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    (feature_dir / "spec.md").write_text(
        "# Feature Spec\n\nThis is the specification.\n", encoding="utf-8"
    )
    (feature_dir / "plan.md").write_text(
        "# Implementation Plan\n\nThis is the plan.\n", encoding="utf-8"
    )
    (feature_dir / "meta.json").write_text(
        '{"feature_id": "001-test-feature", "target_branch": "main"}\n',
        encoding="utf-8",
    )
    (tasks_dir / "WP01-setup.md").write_text(
        "---\nwork_package_id: WP01\ntitle: Setup\nlane: done\n---\n\n# WP01\n",
        encoding="utf-8",
    )

    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "Add legacy kitty-specs layout"], cwd=repo)


def _create_non_orphan_configured_layout(repo: Path) -> None:
    """Create config + healthy worktree where spec branch is non-orphan."""
    (repo / ".kittify").mkdir(parents=True, exist_ok=True)

    # Create kitty-specs from main (non-orphan by construction).
    _git(["checkout", "-b", "kitty-specs"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)

    # Register a healthy worktree for this non-orphan branch.
    _git(["worktree", "add", str(repo / "kitty-specs"), "kitty-specs"], cwd=repo)

    # Save config pointing at branch + worktree.
    save_spec_storage_config(
        repo,
        SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="kitty-specs",
            auto_push=False,
            is_defaulted=False,
        ),
    )


def _get_log_messages(repo: Path, branch: str = "HEAD") -> list[str]:
    """Return commit messages for the given branch."""
    result = _git(
        ["log", "--format=%s", branch, "--"],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [m.strip() for m in result.stdout.strip().splitlines() if m.strip()]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def legacy_repo(tmp_path: Path) -> Path:
    """Create a repo with the legacy kitty-specs/ layout."""
    repo = _init_repo(tmp_path / "repo")
    _create_legacy_layout(repo)
    return repo


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Path:
    """Create a clean repo without kitty-specs/."""
    return _init_repo(tmp_path / "repo")


@pytest.fixture()
def migration() -> SpecBranchWorktreeMigration:
    """Return a fresh migration instance."""
    return SpecBranchWorktreeMigration()


@pytest.fixture()
def migrated_repo(legacy_repo: Path, migration: SpecBranchWorktreeMigration) -> Path:
    """Create a repo that has already been successfully migrated."""
    result = migration.apply(legacy_repo)
    assert result.success, f"Migration setup failed: {result.errors}"
    return legacy_repo


# ============================================================================
# Issue 1 - _classify() validates worktree health
# ============================================================================


class TestClassifyWorktreeValidation:
    """Verify _classify() checks worktree health, not just config + branch."""

    def test_healthy_worktree_returns_already_migrated(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Fully healthy migration returns STATUS_ALREADY_MIGRATED."""
        status = migration._classify(migrated_repo)
        assert status.status == STATUS_ALREADY_MIGRATED
        assert "healthy" in status.reason.lower()

    def test_missing_worktree_dir_not_already_migrated(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Config + branch but missing worktree directory is NOT already_migrated."""
        # Remove the worktree via git, then delete the directory
        wt_path = migrated_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=migrated_repo)

        status = migration._classify(migrated_repo)
        assert status.status == STATUS_NOT_APPLICABLE
        assert "unhealthy" in status.reason.lower() or "repair" in status.reason.lower()

    def test_worktree_path_conflict_not_already_migrated(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Config + branch but worktree replaced by regular dir is NOT already_migrated."""
        wt_path = migrated_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=migrated_repo)
        # Create a regular directory in its place
        wt_path.mkdir()
        (wt_path / "stray-file.txt").write_text("conflict", encoding="utf-8")

        status = migration._classify(migrated_repo)
        assert status.status == STATUS_NOT_APPLICABLE

    def test_config_without_branch_not_applicable(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Config present but branch missing returns NOT_APPLICABLE."""
        # Write config without creating the branch
        (empty_repo / ".kittify").mkdir(parents=True, exist_ok=True)
        save_spec_storage_config(empty_repo, SpecStorageConfig())

        status = migration._classify(empty_repo)
        assert status.status == STATUS_NOT_APPLICABLE
        assert "missing" in status.reason.lower()

    def test_non_orphan_branch_not_already_migrated(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Config + healthy worktree but non-orphan branch is NOT already_migrated."""
        _create_non_orphan_configured_layout(empty_repo)

        # Confirm scenario has healthy worktree first.
        config = load_spec_storage_config(empty_repo)
        state = discover_spec_worktree(empty_repo, config)
        assert state.health_status == HEALTH_HEALTHY

        # Classification must still reject because branch is non-orphan.
        status = migration._classify(empty_repo)
        assert status.status == STATUS_NOT_APPLICABLE
        assert "not orphan" in status.reason.lower() or "shares ancestry" in status.reason.lower()
        assert migration.detect(empty_repo) is False


# ============================================================================
# Issue 2 - detect/apply round-trip through upgrade runner
# ============================================================================


class TestDetectApplyRoundTrip:
    """Verify detect() returns True for already-migrated so runner passes to apply()."""

    def test_detect_true_for_legacy(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """detect() returns True for legacy layout (needs migration)."""
        assert migration.detect(legacy_repo) is True

    def test_detect_true_for_already_migrated(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """detect() returns True for already-migrated repos."""
        assert migration.detect(migrated_repo) is True

    def test_detect_false_for_clean_repo(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """detect() returns False for repos without kitty-specs/."""
        assert migration.detect(empty_repo) is False

    def test_apply_returns_already_migrated_on_rerun(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """apply() on already-migrated repo returns success with warning."""
        result = migration.apply(migrated_repo)
        assert result.success is True
        assert any("already migrated" in w.lower() for w in result.warnings)
        assert result.changes_made == []  # No mutations

    def test_rerun_makes_no_commits(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Rerun on already-migrated repo does not add commits."""
        main_before = _get_log_messages(migrated_repo, "main")
        spec_before = _get_log_messages(migrated_repo, "kitty-specs")

        migration.apply(migrated_repo)

        main_after = _get_log_messages(migrated_repo, "main")
        spec_after = _get_log_messages(migrated_repo, "kitty-specs")

        assert main_before == main_after
        assert spec_before == spec_after

    def test_runner_applies_already_migrated_path(
        self, migrated_repo: Path
    ):
        """The upgrade runner surfaces already_migrated when re-running."""
        from specify_cli.upgrade.runner import MigrationRunner

        runner = MigrationRunner(migrated_repo)

        # Create .kittify/metadata.yaml so runner can proceed
        metadata = runner._create_initial_metadata("0.15.0")

        # Simulate what the runner does for a single migration
        mig = SpecBranchWorktreeMigration()

        # detect() should return True
        assert mig.detect(migrated_repo) is True

        # can_apply() should return True (already migrated is fine)
        can, reason = mig.can_apply(migrated_repo)
        assert can is True

        # apply() should return success with already_migrated warning
        result = mig.apply(migrated_repo)
        assert result.success is True
        assert any("already migrated" in w.lower() for w in result.warnings)

    def test_detect_false_for_broken_worktree(
        self, migrated_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """detect() returns False when worktree is broken (NOT_APPLICABLE)."""
        # Break the worktree
        wt_path = migrated_repo / "kitty-specs"
        _git(["worktree", "remove", "--force", str(wt_path)], cwd=migrated_repo)

        # detect() should return False since it's NOT_APPLICABLE
        assert migration.detect(migrated_repo) is False


# ============================================================================
# Successful migration (core coverage for test discovery)
# ============================================================================


class TestSuccessfulMigration:
    """Verify core migration succeeds and produces expected state."""

    def test_migration_succeeds(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Full migration completes successfully."""
        result = migration.apply(legacy_repo)
        assert result.success, f"Migration failed: {result.errors}"
        assert len(result.changes_made) > 0

    def test_content_transferred_to_worktree(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Planning artifacts are present in the worktree after migration."""
        migration.apply(legacy_repo)
        wt = legacy_repo / "kitty-specs"
        assert (wt / "001-test-feature" / "spec.md").exists()
        assert (wt / "001-test-feature" / "plan.md").exists()
        assert (wt / "001-test-feature" / "tasks" / "WP01-setup.md").exists()

    def test_kitty_specs_removed_from_planning_branch(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """kitty-specs/ is no longer tracked on the planning branch."""
        migration.apply(legacy_repo)
        tree_result = _git(
            ["ls-tree", "-r", "--name-only", "main"],
            cwd=legacy_repo,
        )
        tracked_files = tree_result.stdout.strip().splitlines()
        kitty_files = [f for f in tracked_files if f.startswith("kitty-specs/")]
        assert kitty_files == []

    def test_spec_storage_config_saved(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """spec_storage config is written after migration."""
        migration.apply(legacy_repo)
        assert has_spec_storage_config(legacy_repo)
        config = load_spec_storage_config(legacy_repo)
        assert config.branch_name == "kitty-specs"
        assert config.auto_push is False

    def test_orphan_branch_is_truly_orphan(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """The spec branch has no common ancestor with main."""
        migration.apply(legacy_repo)
        result = _git(
            ["merge-base", "main", "kitty-specs"],
            cwd=legacy_repo,
            check=False,
        )
        assert result.returncode != 0

    def test_planning_branch_history_preserved(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Planning branch history includes original commits + migration commit."""
        original_messages = _get_log_messages(legacy_repo, "main")
        migration.apply(legacy_repo)
        new_messages = _get_log_messages(legacy_repo, "main")
        assert len(new_messages) == len(original_messages) + 1
        for msg in original_messages:
            assert msg in new_messages

    def test_worktree_healthy_after_migration(
        self, migrated_repo: Path,
    ):
        """Worktree is healthy immediately after migration."""
        config = load_spec_storage_config(migrated_repo)
        state = discover_spec_worktree(migrated_repo, config)
        assert state.health_status == HEALTH_HEALTHY
        assert state.registered is True


# ============================================================================
# Safety guardrails
# ============================================================================


class TestSafetyGuardrails:
    """Verify migration safety checks."""

    def test_blocked_when_dirty(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration is blocked when working tree has uncommitted changes."""
        (legacy_repo / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        _git(["add", "dirty.txt"], cwd=legacy_repo)

        can, reason = migration.can_apply(legacy_repo)
        assert can is False
        assert "stash" in reason.lower() or "uncommitted" in reason.lower()

    def test_no_force_push(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration never uses force push or history rewrite."""
        result = migration.apply(legacy_repo)
        assert result.success
        reflog = _git(["reflog", "show", "main"], cwd=legacy_repo)
        assert "forced-update" not in reflog.stdout.lower()

    def test_dry_run_makes_no_changes(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Dry run reports planned changes without executing them."""
        result = migration.apply(legacy_repo, dry_run=True)
        assert result.success
        assert any("Would" in c for c in result.changes_made)
        # Verify no actual state changes
        assert not has_spec_storage_config(legacy_repo)

    def test_not_applicable_for_empty_repo(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration reports not applicable for repos without kitty-specs/."""
        can, reason = migration.can_apply(empty_repo)
        assert can is False
