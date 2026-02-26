"""Worktree discovery for spec storage branches.

Resolves the actual spec worktree path from authoritative ``git worktree
list`` metadata rather than path assumptions.  This helper is used by
init, check, and migration commands.

Key principles:
- Parse ``git worktree list --porcelain`` for reliable, machine-readable
  output.
- Match the configured branch name to its worktree entry.
- Return normalised absolute paths and a health status enum.
- Keep output deterministic across Linux / macOS / Windows.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from specify_cli.core.spec_storage_config import SpecStorageConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health status constants
# ---------------------------------------------------------------------------

HEALTH_HEALTHY = "healthy"
HEALTH_MISSING_PATH = "missing_path"
HEALTH_MISSING_REGISTRATION = "missing_registration"
HEALTH_WRONG_BRANCH = "wrong_branch"
HEALTH_PATH_CONFLICT = "path_conflict"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SpecWorktreeState:
    """Runtime state of the spec storage worktree.

    Attributes:
        path: Absolute path where the worktree should live (normalised).
        registered: ``True`` if git reports this path in ``worktree list``.
        branch_name: Branch checked out in the worktree, or ``None`` when
            the worktree is not registered.
        is_clean: ``True`` if the worktree has no uncommitted changes.
            Only meaningful when ``registered`` is ``True``.
        has_manual_changes: ``True`` if the worktree has unstaged
            modifications (a subset of "not clean").
        health_status: One of the ``HEALTH_*`` constants describing the
            overall worktree health.
    """

    path: str
    registered: bool
    branch_name: str | None
    is_clean: bool
    has_manual_changes: bool
    health_status: str


# ---------------------------------------------------------------------------
# Git worktree list parser
# ---------------------------------------------------------------------------


@dataclass
class _WorktreeEntry:
    """A single entry parsed from ``git worktree list --porcelain``."""

    path: str
    head: str | None = None
    branch: str | None = None
    is_bare: bool = False
    is_detached: bool = False


def _parse_worktree_list(output: str) -> list[_WorktreeEntry]:
    """Parse ``git worktree list --porcelain`` output into entries.

    Porcelain format (one per worktree, separated by blank lines)::

        worktree /absolute/path
        HEAD <sha>
        branch refs/heads/<name>

        worktree /another/path
        HEAD <sha>
        detached

    """
    entries: list[_WorktreeEntry] = []
    current: _WorktreeEntry | None = None

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            # Blank line = end of entry.
            if current is not None:
                entries.append(current)
                current = None
            continue

        if stripped.startswith("worktree "):
            current = _WorktreeEntry(path=stripped[len("worktree "):])
        elif current is not None:
            if stripped.startswith("HEAD "):
                current.head = stripped[len("HEAD "):]
            elif stripped.startswith("branch "):
                ref = stripped[len("branch "):]
                # Strip refs/heads/ prefix to get short branch name.
                if ref.startswith("refs/heads/"):
                    current.branch = ref[len("refs/heads/"):]
                else:
                    current.branch = ref
            elif stripped == "bare":
                current.is_bare = True
            elif stripped == "detached":
                current.is_detached = True

    # Flush last entry if file does not end with blank line.
    if current is not None:
        entries.append(current)

    return entries


# ---------------------------------------------------------------------------
# Worktree discovery
# ---------------------------------------------------------------------------


def _get_worktree_entries(repo_root: Path) -> list[_WorktreeEntry]:
    """Run ``git worktree list --porcelain`` and return parsed entries."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "git worktree list failed (rc=%d): %s",
            result.returncode,
            result.stderr.strip(),
        )
        return []

    return _parse_worktree_list(result.stdout)


def _check_worktree_clean(worktree_path: Path) -> tuple[bool, bool]:
    """Check if a worktree is clean.

    Returns ``(is_clean, has_manual_changes)`` where *has_manual_changes*
    means there are unstaged modifications (the ``M`` column in porcelain
    v1 output).
    """
    if not worktree_path.is_dir():
        return True, False

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        # Can't determine status; assume not clean.
        return False, False

    lines = [l for l in result.stdout.splitlines() if l.strip()]
    is_clean = len(lines) == 0

    # Check for unstaged modifications (second char == 'M' in porcelain v1).
    has_manual = any(
        len(line) >= 2 and line[1] == "M"
        for line in lines
    )

    return is_clean, has_manual


def discover_spec_worktree(
    repo_root: Path,
    config: SpecStorageConfig,
) -> SpecWorktreeState:
    """Discover spec worktree state from git metadata.

    Uses ``git worktree list --porcelain`` as the authoritative source and
    matches the configured ``branch_name`` to worktree entries.

    Health status determination:
    - ``"healthy"``: registered, branch matches, directory exists.
    - ``"missing_path"``: registered in git but directory doesn't exist.
    - ``"missing_registration"``: expected path exists but not in worktree
      list.
    - ``"wrong_branch"``: worktree exists at expected path but points to a
      different branch.
    - ``"path_conflict"``: expected path exists as a regular directory
      (not a git worktree).

    Args:
        repo_root: Main repository root.
        config: Spec storage configuration.

    Returns:
        Populated ``SpecWorktreeState``.
    """
    expected_abs = (repo_root / config.worktree_path).resolve()
    expected_str = str(expected_abs)
    expected_branch = config.branch_name

    entries = _get_worktree_entries(repo_root)

    # --- Look for a worktree registered at the expected path. ---
    entry_at_path: _WorktreeEntry | None = None
    entry_for_branch: _WorktreeEntry | None = None

    for entry in entries:
        entry_abs = str(Path(entry.path).resolve())
        if entry_abs == expected_str:
            entry_at_path = entry
        if entry.branch == expected_branch:
            entry_for_branch = entry

    # --- Determine health status. ---

    if entry_at_path is not None:
        # Something is registered at the expected path.
        if entry_at_path.branch == expected_branch:
            # Branch matches - check directory.
            if expected_abs.is_dir():
                is_clean, has_manual = _check_worktree_clean(expected_abs)
                return SpecWorktreeState(
                    path=expected_str,
                    registered=True,
                    branch_name=entry_at_path.branch,
                    is_clean=is_clean,
                    has_manual_changes=has_manual,
                    health_status=HEALTH_HEALTHY,
                )
            else:
                # Registered but directory missing (pruned or deleted).
                return SpecWorktreeState(
                    path=expected_str,
                    registered=True,
                    branch_name=entry_at_path.branch,
                    is_clean=True,
                    has_manual_changes=False,
                    health_status=HEALTH_MISSING_PATH,
                )
        else:
            # Path exists in worktree list but with a different branch.
            is_clean, has_manual = _check_worktree_clean(expected_abs)
            return SpecWorktreeState(
                path=expected_str,
                registered=True,
                branch_name=entry_at_path.branch,
                is_clean=is_clean,
                has_manual_changes=has_manual,
                health_status=HEALTH_WRONG_BRANCH,
            )

    # No worktree registered at the expected path.
    if expected_abs.is_dir():
        # Directory exists but is not a worktree.
        # Check if it looks like a git worktree (.git file) or just a dir.
        git_marker = expected_abs / ".git"
        if git_marker.is_file():
            # It's a git worktree, but not registered at this path somehow.
            is_clean, has_manual = _check_worktree_clean(expected_abs)
            return SpecWorktreeState(
                path=expected_str,
                registered=False,
                branch_name=None,
                is_clean=is_clean,
                has_manual_changes=has_manual,
                health_status=HEALTH_MISSING_REGISTRATION,
            )
        else:
            # Regular directory, not a worktree at all.
            return SpecWorktreeState(
                path=expected_str,
                registered=False,
                branch_name=None,
                is_clean=True,
                has_manual_changes=False,
                health_status=HEALTH_PATH_CONFLICT,
            )

    # Path doesn't exist and not registered - use branch info if available.
    if entry_for_branch is not None:
        # Branch is checked out somewhere else - healthy but at a
        # different path than expected.
        actual_path = str(Path(entry_for_branch.path).resolve())
        is_clean, has_manual = _check_worktree_clean(
            Path(entry_for_branch.path)
        )
        return SpecWorktreeState(
            path=actual_path,
            registered=True,
            branch_name=entry_for_branch.branch,
            is_clean=is_clean,
            has_manual_changes=has_manual,
            health_status=HEALTH_HEALTHY,
        )

    # Nothing found at all - missing registration, no directory.
    return SpecWorktreeState(
        path=expected_str,
        registered=False,
        branch_name=None,
        is_clean=True,
        has_manual_changes=False,
        health_status=HEALTH_MISSING_REGISTRATION,
    )


__all__ = [
    "HEALTH_HEALTHY",
    "HEALTH_MISSING_PATH",
    "HEALTH_MISSING_REGISTRATION",
    "HEALTH_PATH_CONFLICT",
    "HEALTH_WRONG_BRANCH",
    "SpecWorktreeState",
    "discover_spec_worktree",
]
