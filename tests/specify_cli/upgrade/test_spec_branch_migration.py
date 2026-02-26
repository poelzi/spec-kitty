"""Integration tests for the spec branch worktree migration (WP04).

Tests use real temporary git repos (``tmp_path`` + ``subprocess.run``)
to exercise the full migration lifecycle including:
- Successful migration from legacy layout
- Already-migrated rerun (idempotent)
- Blocked when dirty state
- Planning branch history preserved
- Not applicable for non-legacy repos

These tests run actual git commands - no mocking of git operations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_storage_config import (
    has_spec_storage_config,
    load_spec_storage_config,
)
from specify_cli.upgrade.migrations.m_0_16_0_spec_branch_worktree import (
    STATUS_ALREADY_MIGRATED,
    STATUS_NOT_APPLICABLE,
    STATUS_SUCCESS,
    SpecBranchWorktreeMigration,
    _is_working_tree_clean,
    _kitty_specs_tracked,
)


# ============================================================================
# Helpers
# ============================================================================


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
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
    """Create a legacy kitty-specs/ directory tracked on the planning branch.

    Simulates the old layout where planning artifacts live in kitty-specs/
    tracked directly on the development branch.
    """
    # Create .kittify directory (needed for config operations)
    kittify = repo / ".kittify"
    kittify.mkdir(parents=True, exist_ok=True)

    # Create kitty-specs/ with some realistic content
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
    (tasks_dir / "WP02-core.md").write_text(
        "---\nwork_package_id: WP02\ntitle: Core\nlane: doing\n---\n\n# WP02\n",
        encoding="utf-8",
    )

    # Commit the legacy layout
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "Add legacy kitty-specs layout"], cwd=repo)


def _get_branch_list(repo: Path) -> list[str]:
    """Return list of branch names in the repo."""
    result = _git(["branch", "--list", "--format=%(refname:short)"], cwd=repo)
    return [b.strip() for b in result.stdout.strip().splitlines() if b.strip()]


def _get_log_messages(repo: Path, branch: str = "HEAD") -> list[str]:
    """Return commit messages for the given branch.

    Uses ``--`` to disambiguate branch names from paths (e.g. when
    ``kitty-specs`` is both a branch and a directory/worktree).
    """
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


# ============================================================================
# T019 - Legacy detection and already-migrated no-op
# ============================================================================


class TestDetection:
    """Test legacy detection and classification logic."""

    def test_detects_legacy_layout(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration is detected as needed for repos with tracked kitty-specs/."""
        assert migration.detect(legacy_repo) is True

    def test_not_detected_for_clean_repo(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration is not detected for repos without kitty-specs/."""
        assert migration.detect(empty_repo) is False

    def test_classify_legacy(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Classification returns SUCCESS for legacy layout."""
        status = migration._classify(legacy_repo)
        assert status.status == STATUS_SUCCESS

    def test_classify_not_applicable(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Classification returns NOT_APPLICABLE for clean repos."""
        status = migration._classify(empty_repo)
        assert status.status == STATUS_NOT_APPLICABLE

    def test_classify_already_migrated(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """After successful migration, classification returns ALREADY_MIGRATED."""
        # First, apply the migration
        result = migration.apply(legacy_repo)
        assert result.success, f"Migration failed: {result.errors}"

        # Now check classification
        status = migration._classify(legacy_repo)
        assert status.status == STATUS_ALREADY_MIGRATED


# ============================================================================
# T020 - Artifact transfer and planning-branch cleanup
# ============================================================================


class TestSuccessfulMigration:
    """Test full migration from legacy layout."""

    def test_migration_succeeds(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Full migration completes successfully."""
        result = migration.apply(legacy_repo)

        assert result.success, f"Migration failed: {result.errors}"
        assert len(result.changes_made) > 0
        assert len(result.errors) == 0

    def test_orphan_branch_created(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Orphan branch 'kitty-specs' is created."""
        migration.apply(legacy_repo)

        branches = _get_branch_list(legacy_repo)
        assert "kitty-specs" in branches

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
        assert result.returncode != 0, "Branch should be orphan (no common ancestor)"

    def test_content_transferred(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Planning artifacts are present in the worktree."""
        migration.apply(legacy_repo)

        wt = legacy_repo / "kitty-specs"
        assert wt.is_dir(), "Worktree directory should exist"
        assert (wt / "001-test-feature" / "spec.md").exists()
        assert (wt / "001-test-feature" / "plan.md").exists()
        assert (wt / "001-test-feature" / "meta.json").exists()
        assert (wt / "001-test-feature" / "tasks" / "WP01-setup.md").exists()
        assert (wt / "001-test-feature" / "tasks" / "WP02-core.md").exists()

    def test_content_preserved(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Content in transferred files matches the original."""
        # Read original content before migration
        orig_spec = (legacy_repo / "kitty-specs" / "001-test-feature" / "spec.md").read_text(
            encoding="utf-8"
        )
        orig_plan = (legacy_repo / "kitty-specs" / "001-test-feature" / "plan.md").read_text(
            encoding="utf-8"
        )

        migration.apply(legacy_repo)

        wt = legacy_repo / "kitty-specs"
        assert (wt / "001-test-feature" / "spec.md").read_text(encoding="utf-8") == orig_spec
        assert (wt / "001-test-feature" / "plan.md").read_text(encoding="utf-8") == orig_plan

    def test_kitty_specs_removed_from_planning_branch(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """kitty-specs/ is no longer tracked on the planning branch."""
        migration.apply(legacy_repo)

        # Check that kitty-specs/ is not tracked in git on main
        result = _git(
            ["ls-files", "--error-unmatch", "kitty-specs/"],
            cwd=legacy_repo,
            check=False,
        )
        # ls-files should fail because it's no longer tracked
        # Note: After migration, kitty-specs/ is a worktree, so we check
        # the main branch tree directly
        tree_result = _git(
            ["ls-tree", "-r", "--name-only", "main"],
            cwd=legacy_repo,
        )
        tracked_files = tree_result.stdout.strip().splitlines()
        kitty_files = [f for f in tracked_files if f.startswith("kitty-specs/")]
        assert kitty_files == [], f"kitty-specs/ files still tracked on main: {kitty_files}"

    def test_spec_storage_config_saved(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """spec_storage config is written to .kittify/config.yaml."""
        migration.apply(legacy_repo)

        assert has_spec_storage_config(legacy_repo)
        config = load_spec_storage_config(legacy_repo)
        assert config.branch_name == "kitty-specs"
        assert config.worktree_path == "kitty-specs"
        assert config.auto_push is False
        assert config.is_defaulted is False

    def test_worktree_registered(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """The worktree is properly registered with git."""
        migration.apply(legacy_repo)

        result = _git(["worktree", "list", "--porcelain"], cwd=legacy_repo)
        assert "kitty-specs" in result.stdout

    def test_planning_branch_history_preserved(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """The planning branch history includes original commits + migration commit."""
        # Record original commit messages
        original_messages = _get_log_messages(legacy_repo, "main")
        assert len(original_messages) >= 2  # Initial + legacy layout

        migration.apply(legacy_repo)

        # Check main branch still has all original commits plus migration commit
        new_messages = _get_log_messages(legacy_repo, "main")
        assert len(new_messages) == len(original_messages) + 1
        # Migration commit should be the most recent
        assert "migrate" in new_messages[0].lower() or "kitty-specs" in new_messages[0].lower()
        # Original messages should still be present
        for msg in original_messages:
            assert msg in new_messages

    def test_dry_run_makes_no_changes(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Dry run reports what would happen without making changes."""
        result = migration.apply(legacy_repo, dry_run=True)

        assert result.success
        assert len(result.changes_made) > 0
        assert any("Would" in c for c in result.changes_made)

        # Verify nothing actually changed
        assert _kitty_specs_tracked(legacy_repo)
        assert not has_spec_storage_config(legacy_repo)

    def test_spec_branch_has_content_commit(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """The spec branch has commits with the migrated content."""
        migration.apply(legacy_repo)

        messages = _get_log_messages(legacy_repo, "kitty-specs")
        assert len(messages) >= 1
        # Should have at least the initial commit and the content import
        assert any("import" in m.lower() or "initialize" in m.lower() for m in messages)


# ============================================================================
# T019 + T022 - Idempotent rerun
# ============================================================================


class TestIdempotent:
    """Test that re-running the migration is safe."""

    def test_rerun_reports_already_migrated(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Second run returns success with already_migrated status."""
        # First run
        result1 = migration.apply(legacy_repo)
        assert result1.success

        # Second run
        result2 = migration.apply(legacy_repo)
        assert result2.success
        assert any("already migrated" in w.lower() for w in result2.warnings), (
            f"Expected 'already migrated' warning, got: {result2.warnings}"
        )

    def test_rerun_makes_no_changes(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Second run does not create additional commits."""
        migration.apply(legacy_repo)

        main_messages_before = _get_log_messages(legacy_repo, "main")
        spec_messages_before = _get_log_messages(legacy_repo, "kitty-specs")

        migration.apply(legacy_repo)

        main_messages_after = _get_log_messages(legacy_repo, "main")
        spec_messages_after = _get_log_messages(legacy_repo, "kitty-specs")

        assert main_messages_before == main_messages_after
        assert spec_messages_before == spec_messages_after

    def test_can_apply_returns_true_for_already_migrated(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """can_apply returns True even for already-migrated repos."""
        migration.apply(legacy_repo)

        can, reason = migration.can_apply(legacy_repo)
        assert can is True


# ============================================================================
# T021 - Safety guardrails
# ============================================================================


class TestSafetyGuardrails:
    """Test migration safety checks."""

    def test_blocked_when_dirty(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration is blocked when working tree has uncommitted changes."""
        # Create uncommitted changes
        (legacy_repo / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        _git(["add", "dirty.txt"], cwd=legacy_repo)

        can, reason = migration.can_apply(legacy_repo)
        assert can is False
        assert "uncommitted" in reason.lower() or "dirty" in reason.lower() or "stash" in reason.lower()

    def test_blocked_when_unstaged_changes(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration is blocked when there are unstaged modifications."""
        # Modify a tracked file without staging
        (legacy_repo / "README.md").write_text("modified", encoding="utf-8")

        can, reason = migration.can_apply(legacy_repo)
        assert can is False

    def test_no_force_push(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration never uses force push or history rewrite."""
        result = migration.apply(legacy_repo)
        assert result.success

        # Verify no force operations were used by checking reflog
        # (force operations would show "forced-update" entries)
        reflog = _git(["reflog", "show", "main"], cwd=legacy_repo)
        assert "forced-update" not in reflog.stdout.lower()

    def test_remediation_steps_in_error(
        self, legacy_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Error messages include remediation steps."""
        # Create dirty state
        (legacy_repo / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        _git(["add", "dirty.txt"], cwd=legacy_repo)

        can, reason = migration.can_apply(legacy_repo)
        assert can is False
        # Should contain actionable remediation
        assert "stash" in reason.lower() or "commit" in reason.lower()

    def test_not_applicable_for_empty_repo(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration reports not applicable for repos without kitty-specs/."""
        can, reason = migration.can_apply(empty_repo)
        assert can is False
        assert "not applicable" in reason.lower() or "no tracked" in reason.lower()

    def test_apply_not_applicable_succeeds_gracefully(
        self, empty_repo: Path, migration: SpecBranchWorktreeMigration
    ):
        """Applying to a non-applicable repo succeeds with a warning."""
        result = migration.apply(empty_repo)
        assert result.success
        assert len(result.warnings) > 0


# ============================================================================
# T022 - Edge cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_existing_orphan_branch_reused(self, tmp_path: Path, migration: SpecBranchWorktreeMigration):
        """If orphan branch already exists, it's reused (not recreated)."""
        repo = _init_repo(tmp_path / "repo")

        # Pre-create an orphan branch
        _git(["checkout", "--orphan", "kitty-specs"], cwd=repo)
        _git(["rm", "-rf", "."], cwd=repo, check=False)
        _git(
            ["commit", "--allow-empty", "-m", "pre-existing orphan"],
            cwd=repo,
        )
        _git(["checkout", "main"], cwd=repo)

        # Now create legacy layout
        _create_legacy_layout(repo)

        result = migration.apply(repo)
        assert result.success
        assert any("already exists" in c.lower() for c in result.changes_made)

    def test_multiple_features(self, tmp_path: Path, migration: SpecBranchWorktreeMigration):
        """Migration handles multiple feature directories under kitty-specs/."""
        repo = _init_repo(tmp_path / "repo")
        (repo / ".kittify").mkdir(exist_ok=True)

        # Create multiple features
        for i in range(3):
            feature_dir = repo / "kitty-specs" / f"00{i+1}-feature-{i+1}"
            tasks_dir = feature_dir / "tasks"
            tasks_dir.mkdir(parents=True)
            (feature_dir / "spec.md").write_text(
                f"# Feature {i+1}\n", encoding="utf-8"
            )
            (tasks_dir / "WP01.md").write_text(
                f"# WP01 for feature {i+1}\n", encoding="utf-8"
            )

        _git(["add", "."], cwd=repo)
        _git(["commit", "-m", "Add multiple features"], cwd=repo)

        result = migration.apply(repo)
        assert result.success

        # Verify all features are present in worktree
        wt = repo / "kitty-specs"
        for i in range(3):
            assert (wt / f"00{i+1}-feature-{i+1}" / "spec.md").exists()
            assert (wt / f"00{i+1}-feature-{i+1}" / "tasks" / "WP01.md").exists()

    def test_empty_kitty_specs_dir(
        self, tmp_path: Path, migration: SpecBranchWorktreeMigration
    ):
        """Migration handles an empty kitty-specs/ directory."""
        repo = _init_repo(tmp_path / "repo")
        (repo / ".kittify").mkdir(exist_ok=True)

        specs_dir = repo / "kitty-specs"
        specs_dir.mkdir()
        (specs_dir / ".gitkeep").write_text("", encoding="utf-8")

        _git(["add", "."], cwd=repo)
        _git(["commit", "-m", "Add empty kitty-specs"], cwd=repo)

        result = migration.apply(repo)
        assert result.success


# ============================================================================
# Helper function tests
# ============================================================================


class TestHelpers:
    """Test internal helper functions."""

    def test_is_working_tree_clean_on_clean_repo(self, tmp_path: Path):
        """_is_working_tree_clean returns True for clean repos."""
        repo = _init_repo(tmp_path / "repo")
        assert _is_working_tree_clean(repo) is True

    def test_is_working_tree_clean_on_dirty_repo(self, tmp_path: Path):
        """_is_working_tree_clean returns False for dirty repos."""
        repo = _init_repo(tmp_path / "repo")
        (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        assert _is_working_tree_clean(repo) is False

    def test_kitty_specs_tracked_positive(self, legacy_repo: Path):
        """_kitty_specs_tracked returns True when tracked."""
        assert _kitty_specs_tracked(legacy_repo) is True

    def test_kitty_specs_tracked_negative(self, empty_repo: Path):
        """_kitty_specs_tracked returns False when not tracked."""
        assert _kitty_specs_tracked(empty_repo) is False
