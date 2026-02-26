"""Spec storage health check and repair (WP05).

Combines config, branch, and worktree state into a unified health report.
Provides auto-repair for safe failure states and a preflight function
that commands can call before writing to spec storage.

Key principles:
- Health classification is deterministic and based on observable state.
- Repairs are conservative: only re-create missing worktrees, re-register
  unregistered worktrees, or bootstrap from an existing orphan branch.
- Path conflicts (regular directory at the expected worktree path) are
  never auto-repaired - they require manual resolution.
- The preflight function is a reusable building block; commands wire it
  in gradually.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from specify_cli.core.git_ops import SpecBranchState, inspect_spec_branch
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    has_spec_storage_config,
    load_spec_storage_config,
    get_spec_worktree_abs_path,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    HEALTH_PATH_CONFLICT,
    HEALTH_WRONG_BRANCH,
    SpecWorktreeState,
    discover_spec_worktree,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Health status constants
# ---------------------------------------------------------------------------

STATUS_HEALTHY = "healthy"
STATUS_REPAIRABLE = "repairable"
STATUS_CONFLICT = "conflict"
STATUS_NOT_CONFIGURED = "not_configured"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SpecStorageHealthReport:
    """Full health report combining config, branch, and worktree state.

    Attributes:
        config_present: True when the ``spec_storage`` section exists in
            ``.kittify/config.yaml``.
        branch_state: Result of ``inspect_spec_branch``, or None when
            config is absent.
        worktree_state: Result of ``discover_spec_worktree``, or None
            when config is absent.
        health_status: One of ``STATUS_*`` constants:
            - ``"healthy"`` - everything is in order.
            - ``"repairable"`` - safe auto-repair is available.
            - ``"conflict"`` - manual resolution required.
            - ``"not_configured"`` - legacy layout, no spec_storage config.
        issues: Human-readable list of detected problems.
        repairs_available: Human-readable list of repairs that can be
            attempted by ``repair_spec_storage``.
    """

    config_present: bool
    branch_state: SpecBranchState | None
    worktree_state: SpecWorktreeState | None
    health_status: str  # STATUS_HEALTHY | STATUS_REPAIRABLE | STATUS_CONFLICT | STATUS_NOT_CONFIGURED
    issues: list[str] = field(default_factory=list)
    repairs_available: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def check_spec_storage_health(repo_root: Path) -> SpecStorageHealthReport:
    """Full health check combining config, branch, and worktree state.

    Steps:
    1. Check whether ``spec_storage`` config exists.
    2. If not configured, return ``not_configured`` immediately.
    3. Inspect the orphan branch.
    4. Discover the worktree state.
    5. Classify the combined state into a health status.

    Args:
        repo_root: Main repository root.

    Returns:
        Populated ``SpecStorageHealthReport``.
    """
    config_present = has_spec_storage_config(repo_root)

    if not config_present:
        return SpecStorageHealthReport(
            config_present=False,
            branch_state=None,
            worktree_state=None,
            health_status=STATUS_NOT_CONFIGURED,
            issues=["No spec_storage configuration found (legacy or new project)."],
            repairs_available=[],
        )

    config = load_spec_storage_config(repo_root)
    branch_state = inspect_spec_branch(repo_root, config.branch_name)
    worktree_state = discover_spec_worktree(repo_root, config)

    issues: list[str] = []
    repairs: list[str] = []

    # --- Branch-level checks ---
    if not branch_state.exists_local:
        issues.append(
            f"Orphan branch '{config.branch_name}' does not exist locally."
        )
        # No repair if branch is missing entirely - need full bootstrap
        # (unless remote exists, which is a different story)
        if branch_state.exists_remote:
            repairs.append(
                f"Fetch and create local branch '{config.branch_name}' from remote."
            )
        # Without a branch, worktree repair is not possible
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_REPAIRABLE if branch_state.exists_remote else STATUS_CONFLICT,
            issues=issues,
            repairs_available=repairs,
        )

    # --- Worktree-level checks ---
    wt_health = worktree_state.health_status

    if wt_health == HEALTH_HEALTHY:
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_HEALTHY,
            issues=[],
            repairs_available=[],
        )

    if wt_health == HEALTH_MISSING_PATH:
        issues.append(
            "Worktree is registered in git but directory is missing."
        )
        repairs.append(
            "Prune stale worktree registration, then re-add worktree."
        )
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_REPAIRABLE,
            issues=issues,
            repairs_available=repairs,
        )

    if wt_health == HEALTH_MISSING_REGISTRATION:
        expected_abs = get_spec_worktree_abs_path(repo_root, config)
        if expected_abs.is_dir():
            issues.append(
                "Worktree directory exists but is not registered in git."
            )
            repairs.append(
                "Re-register the worktree directory with git."
            )
        else:
            issues.append(
                "Worktree is not registered and directory does not exist."
            )
            repairs.append(
                f"Create worktree at '{config.worktree_path}' for branch "
                f"'{config.branch_name}'."
            )
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_REPAIRABLE,
            issues=issues,
            repairs_available=repairs,
        )

    if wt_health == HEALTH_WRONG_BRANCH:
        issues.append(
            f"Worktree at configured path points to branch "
            f"'{worktree_state.branch_name}' instead of "
            f"'{config.branch_name}'."
        )
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_CONFLICT,
            issues=issues,
            repairs_available=[],
        )

    if wt_health == HEALTH_PATH_CONFLICT:
        expected_abs = get_spec_worktree_abs_path(repo_root, config)
        issues.append(
            f"Path '{config.worktree_path}' exists as a regular directory "
            f"(not a git worktree)."
        )
        issues.append(
            f"Remediation: rename or move '{expected_abs}', then retry."
        )
        return SpecStorageHealthReport(
            config_present=True,
            branch_state=branch_state,
            worktree_state=worktree_state,
            health_status=STATUS_CONFLICT,
            issues=issues,
            repairs_available=[],
        )

    # Catch-all for unexpected worktree health states
    issues.append(f"Unexpected worktree health status: {wt_health}")
    return SpecStorageHealthReport(
        config_present=True,
        branch_state=branch_state,
        worktree_state=worktree_state,
        health_status=STATUS_CONFLICT,
        issues=issues,
        repairs_available=[],
    )


# ---------------------------------------------------------------------------
# Auto-repair
# ---------------------------------------------------------------------------


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


def _fetch_remote_branch(
    repo_root: Path,
    branch_name: str,
    remote: str = "origin",
) -> bool:
    """Fetch a remote branch and create the local tracking branch.

    Returns True on success.
    """
    try:
        _run_git(
            ["fetch", remote, f"{branch_name}:{branch_name}"],
            cwd=repo_root,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        logger.warning("Failed to fetch %s/%s", remote, branch_name)
        return False


def _prune_and_readd_worktree(
    repo_root: Path,
    config: SpecStorageConfig,
) -> bool:
    """Prune stale worktree registration and re-add from the branch.

    Used when git knows about the worktree but the directory is gone.
    Returns True on success.
    """
    try:
        # Prune stale entries
        _run_git(["worktree", "prune"], cwd=repo_root, check=True)

        # Re-add worktree
        worktree_abs = get_spec_worktree_abs_path(repo_root, config)
        _run_git(
            ["worktree", "add", str(worktree_abs), config.branch_name],
            cwd=repo_root,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to prune and re-add worktree: %s", exc)
        return False


def _repair_missing_registration(
    repo_root: Path,
    config: SpecStorageConfig,
) -> bool:
    """Repair a worktree that exists on disk but is not registered.

    Strategy depends on whether the directory exists:
    - If directory exists with a .git file: remove and re-add (the stale
      .git file will be replaced by git worktree add).
    - If directory does not exist: simply add a new worktree.

    Returns True on success.
    """
    worktree_abs = get_spec_worktree_abs_path(repo_root, config)

    try:
        if worktree_abs.is_dir():
            # The directory has a stale .git file. Remove it so
            # git worktree add can create a fresh checkout.
            git_marker = worktree_abs / ".git"
            if git_marker.is_file():
                git_marker.unlink()

            # Prune any stale entries first
            _run_git(["worktree", "prune"], cwd=repo_root, check=False)

            # Try repair via git worktree repair (Git 2.35+)
            result = _run_git(
                ["worktree", "repair"],
                cwd=repo_root,
                check=False,
            )
            if result.returncode == 0:
                # Check if the worktree is now registered
                from specify_cli.core.spec_worktree_discovery import discover_spec_worktree
                state = discover_spec_worktree(repo_root, config)
                if state.health_status == HEALTH_HEALTHY:
                    return True

            # Repair didn't work, try removing the directory contents
            # and re-adding. We only do this if the dir is effectively
            # empty or only has the stale .git.
            import shutil
            shutil.rmtree(worktree_abs, ignore_errors=True)

        # Add worktree from scratch
        _run_git(
            ["worktree", "add", str(worktree_abs), config.branch_name],
            cwd=repo_root,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to repair missing registration: %s", exc)
        return False


def repair_spec_storage(
    repo_root: Path,
    report: SpecStorageHealthReport,
) -> bool:
    """Attempt automatic repair for safe failure states.

    Only repairs states classified as ``STATUS_REPAIRABLE``. Returns
    ``True`` on success, ``False`` on failure. Never modifies state
    classified as ``STATUS_CONFLICT``.

    Safe repairs:
    - Re-create missing worktree path (prune + re-add).
    - Re-register missing worktree registration.
    - Fetch remote branch to create local copy.

    Args:
        repo_root: Main repository root.
        report: Health report from ``check_spec_storage_health``.

    Returns:
        ``True`` if the repair succeeded, ``False`` otherwise.
    """
    if report.health_status != STATUS_REPAIRABLE:
        logger.info(
            "Cannot repair: status is %s (not repairable)",
            report.health_status,
        )
        return False

    config = load_spec_storage_config(repo_root)

    # --- Branch missing locally but exists on remote ---
    if report.branch_state and not report.branch_state.exists_local:
        if report.branch_state.exists_remote:
            if not _fetch_remote_branch(repo_root, config.branch_name):
                return False
            # After fetching, we need to also set up the worktree
            worktree_abs = get_spec_worktree_abs_path(repo_root, config)
            if not worktree_abs.is_dir():
                try:
                    _run_git(
                        ["worktree", "add", str(worktree_abs), config.branch_name],
                        cwd=repo_root,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    return False
            return True
        # No remote branch either - cannot repair
        return False

    # --- Worktree repairs ---
    if report.worktree_state is None:
        return False

    wt_health = report.worktree_state.health_status

    if wt_health == HEALTH_MISSING_PATH:
        return _prune_and_readd_worktree(repo_root, config)

    if wt_health == HEALTH_MISSING_REGISTRATION:
        return _repair_missing_registration(repo_root, config)

    logger.warning(
        "No repair strategy for worktree health %s", wt_health
    )
    return False


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def ensure_spec_storage_ready(
    repo_root: Path,
    console: Console | None = None,
) -> Path | None:
    """Run health check, auto-repair if possible, return spec root path.

    This is a reusable preflight function that spec-modifying commands
    can call before they write. It:

    1. Runs ``check_spec_storage_health``.
    2. If healthy, returns the worktree path immediately.
    3. If repairable, attempts ``repair_spec_storage``.
    4. If repair succeeds, returns the worktree path.
    5. If not configured, returns the legacy ``kitty-specs/`` path
       (for backward compatibility).
    6. Otherwise returns ``None`` and prints guidance.

    Args:
        repo_root: Main repository root.
        console: Optional Rich console for user-facing output.

    Returns:
        Absolute path to the spec storage root, or ``None`` on failure.
    """
    report = check_spec_storage_health(repo_root)

    if report.health_status == STATUS_HEALTHY:
        config = load_spec_storage_config(repo_root)
        return get_spec_worktree_abs_path(repo_root, config)

    if report.health_status == STATUS_NOT_CONFIGURED:
        # Legacy layout - return traditional kitty-specs/ path
        legacy_path = repo_root / "kitty-specs"
        if legacy_path.is_dir():
            return legacy_path
        return None

    if report.health_status == STATUS_REPAIRABLE:
        if console:
            console.print(
                "[yellow]Spec storage needs repair. Attempting auto-repair...[/yellow]"
            )
            for issue in report.issues:
                console.print(f"  [dim]Issue: {issue}[/dim]")

        success = repair_spec_storage(repo_root, report)

        if success:
            if console:
                console.print(
                    "[green]Spec storage repaired successfully.[/green]"
                )
            config = load_spec_storage_config(repo_root)
            return get_spec_worktree_abs_path(repo_root, config)
        else:
            if console:
                console.print(
                    "[red]Auto-repair failed. Manual intervention required.[/red]"
                )
            return None

    # STATUS_CONFLICT or unknown
    if console:
        console.print(
            "[red]Spec storage has conflicts that cannot be auto-repaired.[/red]"
        )
        for issue in report.issues:
            console.print(f"  [red]• {issue}[/red]")
    return None


__all__ = [
    "STATUS_CONFLICT",
    "STATUS_HEALTHY",
    "STATUS_NOT_CONFIGURED",
    "STATUS_REPAIRABLE",
    "SpecStorageHealthReport",
    "check_spec_storage_health",
    "ensure_spec_storage_ready",
    "repair_spec_storage",
]
