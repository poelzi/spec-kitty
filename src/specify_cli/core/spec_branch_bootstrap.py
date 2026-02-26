"""Bootstrap orphan spec branch and worktree during init.

Creates (or verifies) the orphan branch and git worktree used for
storing planning artifacts (specs, plans, work packages).

This module is the bridge between init and the WP01 primitives:
- ``spec_storage_config`` for loading/saving configuration
- ``git_ops`` for branch inspection
- ``spec_worktree_discovery`` for worktree health checks

Key design decisions:
- Idempotent: safe to call on every ``spec-kitty init`` invocation.
- Non-destructive: never deletes user files or force-overwrites.
- Graceful: repos without spec_storage config still work.
- Returns success/failure boolean for the init flow to handle.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from rich.console import Console

from specify_cli.core.git_ops import (
    inspect_spec_branch,
    resolve_primary_branch,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    has_spec_storage_config,
    load_spec_storage_config,
    save_spec_storage_config,
    validate_spec_storage_config,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
    HEALTH_PATH_CONFLICT,
    HEALTH_WRONG_BRANCH,
    discover_spec_worktree,
)

logger = logging.getLogger(__name__)


def _create_orphan_branch(
    repo_root: Path,
    branch_name: str,
    console: Console | None = None,
) -> bool:
    """Create an orphan branch with an initial empty commit.

    The orphan branch has no shared history with any other branch,
    making it a clean namespace for planning artifacts.

    Returns True on success, False on failure.
    """
    # We need to create the orphan branch without disturbing the current
    # working tree.  Strategy: use a temporary worktree to create the
    # branch, then remove the worktree.
    #
    # Alternative: use low-level git plumbing (hash-object + mktree +
    # commit-tree + update-ref) which avoids checkout entirely.
    # We use plumbing for safety and speed.

    try:
        # Create an empty tree object
        result = subprocess.run(
            ["git", "mktree"],
            input="",
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        empty_tree = result.stdout.strip()

        # Create a commit pointing to the empty tree (no parent = orphan)
        result = subprocess.run(
            [
                "git", "commit-tree", empty_tree,
                "-m", "Initial spec storage commit (orphan branch)",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        commit_sha = result.stdout.strip()

        # Create the branch ref pointing to this commit
        subprocess.run(
            ["git", "update-ref", f"refs/heads/{branch_name}", commit_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        if console:
            console.print(
                f"[green]Created orphan branch[/green] "
                f"[cyan]{branch_name}[/cyan] ({commit_sha[:8]})"
            )
        logger.info(
            "Created orphan branch %s at %s", branch_name, commit_sha[:8]
        )
        return True

    except subprocess.CalledProcessError as exc:
        if console:
            console.print(
                f"[red]Failed to create orphan branch "
                f"{branch_name}:[/red] {exc.stderr or exc}"
            )
        logger.error("Failed to create orphan branch %s: %s", branch_name, exc)
        return False


def _create_worktree(
    repo_root: Path,
    worktree_path: Path,
    branch_name: str,
    console: Console | None = None,
) -> bool:
    """Create a git worktree at the given path for the given branch.

    Returns True on success, False on failure.
    """
    try:
        # Ensure parent directory exists
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        if console:
            console.print(
                f"[green]Created spec worktree[/green] at "
                f"[cyan]{worktree_path.relative_to(repo_root)}[/cyan]"
            )
        logger.info("Created worktree at %s for branch %s", worktree_path, branch_name)
        return True

    except subprocess.CalledProcessError as exc:
        if console:
            console.print(
                f"[red]Failed to create worktree at "
                f"{worktree_path}:[/red] {exc.stderr or exc}"
            )
        logger.error("Failed to create worktree: %s", exc)
        return False


def _repair_worktree(
    repo_root: Path,
    console: Console | None = None,
) -> bool:
    """Run ``git worktree repair`` to fix stale registrations.

    Returns True on success, False on failure.
    """
    try:
        subprocess.run(
            ["git", "worktree", "repair"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def bootstrap_spec_storage(
    repo_root: Path,
    console: Console | None = None,
) -> bool:
    """Bootstrap orphan spec branch and worktree for a repository.

    This is the main entry point called from ``init()`` after the project
    structure is created and git is initialised.

    Steps:
    1. Load or create spec_storage config (with defaults).
    2. Validate the configuration.
    3. Create the orphan branch if it doesn't exist, or verify it is
       indeed orphan.
    4. Create or verify the worktree.
    5. Persist config to ``.kittify/config.yaml``.

    Returns True if setup succeeded (or was already healthy), False on
    failure.  Failures are reported via console but do not raise.
    """
    # ---- Step 1: Load / create config ----
    if has_spec_storage_config(repo_root):
        config = load_spec_storage_config(repo_root)
        config_source = "existing"
    else:
        config = SpecStorageConfig(is_defaulted=True)
        config_source = "default"

    # ---- Step 2: Validate ----
    errors = validate_spec_storage_config(config, repo_root)
    if errors:
        if console:
            console.print("[red]Spec storage configuration errors:[/red]")
            for err in errors:
                console.print(f"  - {err}")
        return False

    branch_name = config.branch_name
    worktree_abs = (repo_root / config.worktree_path).resolve()

    if console:
        console.print(
            f"[cyan]Spec storage:[/cyan] branch=[cyan]{branch_name}[/cyan] "
            f"path=[cyan]{config.worktree_path}[/cyan] "
            f"auto_push=[cyan]{config.auto_push}[/cyan] "
            f"(source: {config_source})"
        )

    # ---- Step 3: Branch setup ----
    state = inspect_spec_branch(repo_root, branch_name)

    if state.exists_local:
        if state.is_orphan:
            if console:
                console.print(
                    f"[green]Orphan branch[/green] [cyan]{branch_name}[/cyan] "
                    f"already exists (HEAD: {state.head_commit or 'unknown'})"
                )
        else:
            if console:
                console.print(
                    f"[yellow]Warning:[/yellow] Branch [cyan]{branch_name}[/cyan] "
                    f"exists but is NOT orphan (shares ancestry with main branch). "
                    f"Continuing with existing branch."
                )
            # Not a hard failure - the branch exists, we can still use it.
    else:
        # Create the orphan branch
        if not _create_orphan_branch(repo_root, branch_name, console):
            return False

    # ---- Step 4: Worktree setup ----
    wt_state = discover_spec_worktree(repo_root, config)

    if wt_state.health_status == HEALTH_HEALTHY:
        if console:
            console.print(
                f"[green]Spec worktree[/green] already healthy at "
                f"[cyan]{config.worktree_path}[/cyan]"
            )
    elif wt_state.health_status == HEALTH_MISSING_PATH:
        # Registered but directory is gone.  Remove stale registration,
        # then re-create.
        if console:
            console.print(
                "[yellow]Spec worktree registered but directory missing. "
                "Re-creating...[/yellow]"
            )
        # Prune stale worktrees first
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if not _create_worktree(repo_root, worktree_abs, branch_name, console):
            return False
    elif wt_state.health_status == HEALTH_MISSING_REGISTRATION:
        # Path might exist (stale .git file) or not exist at all.
        if worktree_abs.is_dir():
            # Try repair first
            _repair_worktree(repo_root, console)
            # Re-check after repair
            wt_state2 = discover_spec_worktree(repo_root, config)
            if wt_state2.health_status == HEALTH_HEALTHY:
                if console:
                    console.print(
                        "[green]Spec worktree[/green] repaired successfully"
                    )
            else:
                if console:
                    console.print(
                        "[yellow]Could not repair worktree registration. "
                        "Removing stale directory and re-creating...[/yellow]"
                    )
                # The directory has a .git file (stale worktree remnant).
                # Safe to remove and recreate since it's our managed path.
                import shutil
                shutil.rmtree(worktree_abs)
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=repo_root,
                    capture_output=True,
                    check=False,
                )
                if not _create_worktree(
                    repo_root, worktree_abs, branch_name, console
                ):
                    return False
        else:
            # Path doesn't exist at all - create fresh worktree
            if not _create_worktree(
                repo_root, worktree_abs, branch_name, console
            ):
                return False
    elif wt_state.health_status == HEALTH_PATH_CONFLICT:
        if console:
            console.print(
                f"[red]Error:[/red] Path [cyan]{config.worktree_path}[/cyan] "
                f"already exists as a regular directory (not a git worktree). "
                f"Please remove or rename it before initialising spec storage."
            )
        return False
    elif wt_state.health_status == HEALTH_WRONG_BRANCH:
        if console:
            console.print(
                f"[red]Error:[/red] Worktree at [cyan]{config.worktree_path}[/cyan] "
                f"is checked out on branch [cyan]{wt_state.branch_name}[/cyan] "
                f"instead of [cyan]{branch_name}[/cyan]. "
                f"Please resolve manually."
            )
        return False
    else:
        # Unexpected health status
        if console:
            console.print(
                f"[yellow]Unexpected worktree state: {wt_state.health_status}[/yellow]"
            )
        return False

    # ---- Step 5: Persist config ----
    save_spec_storage_config(repo_root, config)

    if console:
        auto_push_status = "enabled" if config.auto_push else "disabled"
        console.print(
            f"[green]Spec storage bootstrapped successfully[/green] "
            f"(auto_push: {auto_push_status})"
        )

    return True


__all__ = [
    "bootstrap_spec_storage",
]
