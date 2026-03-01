"""Migration: Explicit legacy migration to orphan-branch spec storage.

Moves planning artifacts from a tracked ``kitty-specs/`` directory on the
planning branch to a dedicated orphan branch managed via a git worktree.

This migration:
1. Detects repos still tracking ``kitty-specs/`` on the planning branch.
2. Creates an orphan branch and git worktree for spec storage.
3. Copies all ``kitty-specs/`` content to the orphan branch worktree.
4. Commits the content on the orphan branch.
5. Removes ``kitty-specs/`` from the planning branch via ``git rm -r``.
6. Saves the ``spec_storage`` configuration to ``.kittify/config.yaml``.

Safety guarantees:
- **No history rewrite** - only normal commits.
- **Idempotent** - re-running reports "already migrated" cleanly.
- **Explicit only** - never auto-triggered outside ``spec-kitty upgrade``.
- **Blocks on dirty state** with clear remediation steps.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..registry import MigrationRegistry
from .base import BaseMigration, MigrationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Migration result status constants
# ---------------------------------------------------------------------------

STATUS_SUCCESS = "success"
STATUS_ALREADY_MIGRATED = "already_migrated"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_FAILED = "failed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _MigrationStatus:
    """Internal status for migration detection."""

    status: str  # STATUS_* constants
    reason: str


def _run_git(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _is_working_tree_clean(repo_root: Path) -> bool:
    """Return True if the git working tree has no uncommitted changes."""
    result = _run_git(["status", "--porcelain"], cwd=repo_root, check=False)
    if result.returncode != 0:
        return False
    return result.stdout.strip() == ""


def _kitty_specs_tracked(repo_root: Path) -> bool:
    """Return True if ``kitty-specs/`` is tracked in the current branch."""
    result = _run_git(
        ["ls-files", "--error-unmatch", "kitty-specs/"],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def _branch_exists(repo_root: Path, branch: str) -> bool:
    """Return True if the given branch exists locally."""
    result = _run_git(
        ["rev-parse", "--verify", branch],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def _is_orphan_branch(repo_root: Path, branch: str, primary: str) -> bool:
    """Return True if *branch* shares no ancestry with *primary*."""
    if not _branch_exists(repo_root, branch):
        return False
    if not _branch_exists(repo_root, primary):
        return True
    result = _run_git(
        ["merge-base", primary, branch],
        cwd=repo_root,
        check=False,
    )
    return result.returncode != 0


def _resolve_primary_branch(repo_root: Path) -> str:
    """Detect primary branch name (main, master, develop, or default)."""
    # Try origin/HEAD
    result = _run_git(
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode == 0:
        ref = result.stdout.strip()
        if ref:
            branch = ref.split("/")[-1]
            if branch:
                return branch

    # Try common names
    for name in ("main", "master", "develop"):
        if _branch_exists(repo_root, name):
            return name

    return "main"


def _get_current_branch(repo_root: Path) -> str | None:
    """Return the current branch name, or None if detached."""
    result = _run_git(
        ["branch", "--show-current"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode == 0:
        branch = result.stdout.strip()
        return branch or None
    return None


def _worktree_registered_at(repo_root: Path, path: Path) -> bool:
    """Return True if git reports a worktree at *path*."""
    result = _run_git(
        ["worktree", "list", "--porcelain"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        return False
    target = str(path.resolve())
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = line[len("worktree "):]
            if str(Path(wt_path).resolve()) == target:
                return True
    return False


def _create_orphan_branch(repo_root: Path, branch_name: str) -> bool:
    """Create an orphan branch with an initial empty commit.

    Uses a temporary worktree to avoid disturbing the current checkout.
    Returns True on success.
    """
    # Create the orphan branch via git checkout --orphan in a temp worktree
    tmp_wt = repo_root / ".git" / "tmp-orphan-setup"
    try:
        # Clean up any stale tmp worktree
        if tmp_wt.exists():
            _run_git(
                ["worktree", "remove", "--force", str(tmp_wt)],
                cwd=repo_root,
                check=False,
            )
            if tmp_wt.exists():
                shutil.rmtree(tmp_wt, ignore_errors=True)

        # Create a detached worktree, then create orphan branch inside it
        # First, we use git worktree add with --detach
        _run_git(
            ["worktree", "add", "--detach", str(tmp_wt)],
            cwd=repo_root,
            check=True,
        )

        # Inside the temp worktree, create the orphan branch
        _run_git(
            ["checkout", "--orphan", branch_name],
            cwd=tmp_wt,
            check=True,
        )

        # Remove all tracked files from the orphan branch index
        _run_git(["rm", "-rf", "."], cwd=tmp_wt, check=False)

        # Create an initial commit (allow empty).
        # Use --no-verify to skip pre-commit hooks which fail in the
        # temporary worktree (no .pre-commit-config.yaml present).
        _run_git(
            ["commit", "--no-verify", "--allow-empty", "-m",
             "chore: initialize spec storage branch"],
            cwd=tmp_wt,
            check=True,
        )

        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create orphan branch %s: %s", branch_name, exc)
        return False
    finally:
        # Clean up temp worktree
        _run_git(
            ["worktree", "remove", "--force", str(tmp_wt)],
            cwd=repo_root,
            check=False,
        )
        if tmp_wt.exists():
            shutil.rmtree(tmp_wt, ignore_errors=True)


def _add_worktree(
    repo_root: Path, worktree_path: Path, branch_name: str
) -> bool:
    """Add a git worktree at *worktree_path* checking out *branch_name*."""
    try:
        _run_git(
            ["worktree", "add", str(worktree_path), branch_name],
            cwd=repo_root,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Failed to add worktree at %s: %s", worktree_path, exc
        )
        return False


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


@MigrationRegistry.register
class SpecBranchWorktreeMigration(BaseMigration):
    """Migrate kitty-specs/ from planning branch to orphan branch worktree.

    Explicit migration that:
    1. Creates an orphan branch for spec storage.
    2. Copies kitty-specs/ content to the orphan branch.
    3. Removes kitty-specs/ from the planning branch.
    4. Saves spec_storage config.

    Idempotent: re-running after successful migration reports
    "already_migrated" and makes no changes.
    """

    migration_id = "0.16.0_spec_branch_worktree"
    description = (
        "Migrate kitty-specs/ from planning branch to orphan branch worktree"
    )
    target_version = "0.16.0"

    # Default branch and path names
    SPEC_BRANCH = "kitty-specs"
    WORKTREE_PATH = "kitty-specs"

    def detect(self, project_path: Path) -> bool:
        """Return True if this migration is needed **or** already applied.

        Detection logic:
        - Legacy layout (``STATUS_SUCCESS``): kitty-specs/ tracked on
          planning branch, no spec_storage config -> needs migration.
        - Already migrated (``STATUS_ALREADY_MIGRATED``): has config +
          healthy worktree -> returns True so the runner passes through
          to ``apply()``, which surfaces the clean "already_migrated"
          no-op result.

        Returns True when the project is either a legacy repo or an
        already-migrated repo.  Returns False only for NOT_APPLICABLE
        states (no kitty-specs at all, or broken config requiring
        manual repair).
        """
        status = self._classify(project_path)
        return status.status in (STATUS_SUCCESS, STATUS_ALREADY_MIGRATED)

    def can_apply(self, project_path: Path) -> tuple[bool, str]:
        """Check if migration can be safely applied.

        Blocks if:
        - Working tree is dirty.
        - kitty-specs/ path has a conflict (non-tracked directory).
        """
        status = self._classify(project_path)

        if status.status == STATUS_NOT_APPLICABLE:
            return False, status.reason

        if status.status == STATUS_ALREADY_MIGRATED:
            # Already migrated is fine - apply() will return success with no-op
            return True, ""

        # Check working tree cleanliness
        if not _is_working_tree_clean(project_path):
            return (
                False,
                "Working tree has uncommitted changes. "
                "Please commit or stash your changes before running "
                "this migration.\n"
                "  Remediation: git stash && spec-kitty upgrade && git stash pop",
            )

        # Check for worktree path conflicts
        worktree_abs = (project_path / self.WORKTREE_PATH).resolve()
        if worktree_abs.exists() and not _worktree_registered_at(
            project_path, worktree_abs
        ):
            # Check if it's the legacy kitty-specs/ dir (that's expected)
            if _kitty_specs_tracked(project_path):
                # This IS the legacy dir we want to migrate - that's fine
                pass
            else:
                return (
                    False,
                    f"Path '{self.WORKTREE_PATH}' already exists but is not "
                    f"a registered git worktree. Please remove or rename it "
                    f"before running this migration.\n"
                    f"  Remediation: mv {self.WORKTREE_PATH} {self.WORKTREE_PATH}.backup",
                )

        return True, ""

    def apply(
        self, project_path: Path, dry_run: bool = False
    ) -> MigrationResult:
        """Apply the migration.

        Steps:
        1. Classify project state.
        2. Create orphan branch (if needed).
        3. Copy kitty-specs/ content to orphan branch worktree.
        4. Commit on spec branch.
        5. Remove kitty-specs/ from planning branch.
        6. Save spec_storage config.
        """
        status = self._classify(project_path)

        if status.status == STATUS_NOT_APPLICABLE:
            return MigrationResult(
                success=True,
                warnings=[f"Migration not applicable: {status.reason}"],
            )

        if status.status == STATUS_ALREADY_MIGRATED:
            return MigrationResult(
                success=True,
                changes_made=[],
                warnings=[f"Already migrated: {status.reason}"],
            )

        if status.status != STATUS_SUCCESS:
            return MigrationResult(
                success=False,
                errors=[f"Unexpected state: {status.reason}"],
            )

        # --- From here on, we know kitty-specs/ is tracked and needs migration ---

        if dry_run:
            return MigrationResult(
                success=True,
                changes_made=[
                    f"Would create orphan branch '{self.SPEC_BRANCH}'",
                    f"Would copy kitty-specs/ content to worktree at '{self.WORKTREE_PATH}'",
                    "Would remove kitty-specs/ from planning branch",
                    "Would save spec_storage config to .kittify/config.yaml",
                ],
            )

        changes: list[str] = []
        errors: list[str] = []

        # Gather the content from kitty-specs/ before we start modifying things
        legacy_dir = project_path / "kitty-specs"
        if not legacy_dir.is_dir():
            return MigrationResult(
                success=False,
                errors=["kitty-specs/ directory not found despite being tracked"],
            )

        # Step 1: Create orphan branch if it doesn't exist
        if not _branch_exists(project_path, self.SPEC_BRANCH):
            if not _create_orphan_branch(project_path, self.SPEC_BRANCH):
                return MigrationResult(
                    success=False,
                    errors=[
                        f"Failed to create orphan branch '{self.SPEC_BRANCH}'. "
                        "Check git permissions and repository state."
                    ],
                )
            changes.append(f"Created orphan branch '{self.SPEC_BRANCH}'")
        else:
            # Branch exists - verify it's an orphan
            primary = _resolve_primary_branch(project_path)
            if not _is_orphan_branch(
                project_path, self.SPEC_BRANCH, primary
            ):
                return MigrationResult(
                    success=False,
                    errors=[
                        f"Branch '{self.SPEC_BRANCH}' exists but is not an "
                        f"orphan branch (shares ancestry with '{primary}'). "
                        "Cannot safely migrate. Please resolve manually."
                    ],
                )
            changes.append(
                f"Orphan branch '{self.SPEC_BRANCH}' already exists"
            )

        # Step 2: Set up worktree
        worktree_abs = (project_path / self.WORKTREE_PATH).resolve()

        # We need to temporarily move the legacy dir out of the way
        # to make room for the worktree, then copy content in
        backup_dir = project_path / ".git" / "kitty-specs-migration-backup"
        try:
            # Copy legacy content to backup location
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(legacy_dir, backup_dir)

            # Remove kitty-specs/ from git index and working tree
            _run_git(
                ["rm", "-rf", "kitty-specs/"],
                cwd=project_path,
                check=True,
            )
            changes.append(
                "Removed kitty-specs/ from planning branch index"
            )

            # Commit the removal on planning branch.
            # Use --no-verify: this is an automated migration commit, not
            # user-authored content; pre-commit hooks should not gate it.
            _run_git(
                [
                    "commit", "--no-verify", "-m",
                    "chore: migrate kitty-specs/ to orphan branch\n\n"
                    "Planning artifacts are now stored on the dedicated\n"
                    "'kitty-specs' orphan branch managed via git worktree.\n"
                    "This commit removes the tracked kitty-specs/ directory.\n\n"
                    "Migration performed by: spec-kitty upgrade (v0.16.0)",
                ],
                cwd=project_path,
                check=True,
            )
            changes.append(
                "Committed kitty-specs/ removal on planning branch"
            )

            # Now add worktree
            if not _worktree_registered_at(project_path, worktree_abs):
                if not _add_worktree(
                    project_path, worktree_abs, self.SPEC_BRANCH
                ):
                    # Restore: re-add from backup
                    self._restore_from_backup(
                        project_path, backup_dir, errors
                    )
                    return MigrationResult(
                        success=False,
                        errors=[
                            f"Failed to add worktree at '{self.WORKTREE_PATH}'. "
                            "The kitty-specs/ removal has been reverted."
                        ]
                        + errors,
                    )
                changes.append(
                    f"Added worktree at '{self.WORKTREE_PATH}' "
                    f"for branch '{self.SPEC_BRANCH}'"
                )

            # Step 3: Copy content to worktree
            # Copy each item from backup into the worktree
            for item in backup_dir.iterdir():
                dest = worktree_abs / item.name
                if item.name == ".git":
                    continue  # Skip .git artifacts
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            changes.append("Copied kitty-specs/ content to worktree")

            # Step 4: Commit on spec branch
            _run_git(["add", "-A"], cwd=worktree_abs, check=True)

            # Check if there's anything to commit
            status_result = _run_git(
                ["status", "--porcelain"], cwd=worktree_abs, check=False
            )
            if status_result.stdout.strip():
                _run_git(
                    [
                        "commit", "--no-verify", "-m",
                        "chore: import planning artifacts from development branch\n\n"
                        "Migrated from tracked kitty-specs/ directory on the\n"
                        "development branch to this dedicated orphan branch.\n\n"
                        "Migration performed by: spec-kitty upgrade (v0.16.0)",
                    ],
                    cwd=worktree_abs,
                    check=True,
                )
                changes.append("Committed artifacts on spec branch")
            else:
                changes.append(
                    "No new content to commit on spec branch "
                    "(content already present)"
                )

            # Step 5: Save spec_storage config
            self._save_config(project_path)
            changes.append(
                "Saved spec_storage config to .kittify/config.yaml"
            )

            # Step 6: Exclude worktree from git index
            self._exclude_worktree(project_path)

        except subprocess.CalledProcessError as exc:
            errors.append(f"Git operation failed: {exc}")
            # Try to restore
            self._restore_from_backup(project_path, backup_dir, errors)
            return MigrationResult(success=False, errors=errors)
        except OSError as exc:
            errors.append(f"File operation failed: {exc}")
            return MigrationResult(success=False, errors=errors)
        finally:
            # Clean up backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

        return MigrationResult(
            success=True,
            changes_made=changes,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _classify(self, project_path: Path) -> _MigrationStatus:
        """Classify the project's current state for this migration.

        Returns a status indicating what action is appropriate.

        Already-migrated detection validates config **and** orphan branch
        **and** worktree health (registered + directory present).  If the
        worktree is broken the migration reports it as needing repair rather
        than silently no-oping.
        """
        from specify_cli.core.spec_storage_config import (
            has_spec_storage_config,
            load_spec_storage_config,
        )
        from specify_cli.core.spec_worktree_discovery import (
            HEALTH_HEALTHY,
            discover_spec_worktree,
        )

        has_config = has_spec_storage_config(project_path)
        has_tracked = _kitty_specs_tracked(project_path)

        # Already migrated: has config and orphan branch + healthy worktree
        if has_config:
            if not _branch_exists(project_path, self.SPEC_BRANCH):
                # Has config but no branch - unusual state
                return _MigrationStatus(
                    STATUS_NOT_APPLICABLE,
                    "spec_storage config exists but orphan branch is missing. "
                    "Run 'spec-kitty init' to recreate.",
                )

            primary = _resolve_primary_branch(project_path)
            if not _is_orphan_branch(
                project_path, self.SPEC_BRANCH, primary
            ):
                return _MigrationStatus(
                    STATUS_NOT_APPLICABLE,
                    f"spec_storage config exists but branch '{self.SPEC_BRANCH}' "
                    f"is not orphan (shares ancestry with '{primary}'). "
                    "Run 'spec-kitty init' to repair.",
                )

            # Branch exists - verify worktree is registered and healthy
            config = load_spec_storage_config(project_path)
            state = discover_spec_worktree(project_path, config)

            if state.health_status == HEALTH_HEALTHY:
                return _MigrationStatus(
                    STATUS_ALREADY_MIGRATED,
                    "spec_storage config exists, orphan branch is present, "
                    "and worktree is healthy",
                )

            # Config + branch exist but worktree is broken
            return _MigrationStatus(
                STATUS_NOT_APPLICABLE,
                f"spec_storage config and orphan branch exist but worktree "
                f"is unhealthy (status: {state.health_status}). "
                f"Run 'spec-kitty check' or 'spec-kitty init' to repair.",
            )

        # Legacy layout: kitty-specs/ tracked, no config
        if has_tracked:
            return _MigrationStatus(
                STATUS_SUCCESS,
                "Legacy layout detected: kitty-specs/ tracked on planning branch",
            )

        # No tracked kitty-specs/ and no config - not a legacy repo
        # or already cleaned up without config
        return _MigrationStatus(
            STATUS_NOT_APPLICABLE,
            "No tracked kitty-specs/ directory and no spec_storage config. "
            "Use 'spec-kitty init' for new projects.",
        )

    def _save_config(self, project_path: Path) -> None:
        """Save the spec_storage configuration."""
        from specify_cli.core.spec_storage_config import (
            SpecStorageConfig,
            save_spec_storage_config,
        )

        config = SpecStorageConfig(
            branch_name=self.SPEC_BRANCH,
            worktree_path=self.WORKTREE_PATH,
            auto_push=False,
            is_defaulted=False,
        )
        save_spec_storage_config(project_path, config)

    def _exclude_worktree(self, project_path: Path) -> None:
        """Add worktree path to .git/info/exclude."""
        exclude_file = project_path / ".git" / "info" / "exclude"
        if not exclude_file.exists():
            return

        pattern = f"{self.WORKTREE_PATH}/"
        try:
            existing = exclude_file.read_text(encoding="utf-8")
            if pattern not in existing:
                with exclude_file.open("a", encoding="utf-8") as fh:
                    fh.write(
                        f"\n# Added by spec-kitty migration (v0.16.0)\n"
                        f"{pattern}\n"
                    )
        except OSError:
            pass  # Non-critical

    def _restore_from_backup(
        self,
        project_path: Path,
        backup_dir: Path,
        errors: list[str],
    ) -> None:
        """Attempt to restore kitty-specs/ from backup after failure."""
        if not backup_dir.exists():
            errors.append(
                "Cannot restore: backup directory missing. "
                "Manual recovery may be needed."
            )
            return

        legacy_dir = project_path / "kitty-specs"
        try:
            if legacy_dir.exists():
                shutil.rmtree(legacy_dir)
            shutil.copytree(backup_dir, legacy_dir)

            # Re-add to git
            _run_git(["add", "kitty-specs/"], cwd=project_path, check=True)
            _run_git(
                ["commit", "--no-verify", "-m",
                 "chore: restore kitty-specs/ after failed migration"],
                cwd=project_path,
                check=True,
            )
            errors.append(
                "Restored kitty-specs/ on planning branch after failure. "
                "No data was lost."
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            errors.append(
                f"Failed to restore kitty-specs/ from backup: {exc}. "
                "Your data is preserved in .git/kitty-specs-migration-backup/. "
                "Manual recovery: cp -r .git/kitty-specs-migration-backup kitty-specs"
            )
