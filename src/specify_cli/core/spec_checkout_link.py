"""Ensure parallel checkouts share canonical spec storage via symlink.

When users run commands from an additional git checkout created with
``git worktree add`` (outside ``.worktrees/``), this helper ensures the
checkout's ``kitty-specs`` path points at the canonical spec storage
worktree from the main repository.

This prevents accidental creation of an independent planning artifact tree in
parallel checkouts while preserving strict isolation for per-WP workspaces
under ``.worktrees/``.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from specify_cli.core.paths import get_main_repo_root
from specify_cli.core.spec_health import ensure_spec_storage_ready
from specify_cli.core.spec_storage_config import has_spec_storage_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpecsLinkResult:
    """Result of ensuring the checkout-level ``kitty-specs`` symlink."""

    status: str
    checkout_root: Path | None = None
    main_repo_root: Path | None = None
    link_path: Path | None = None
    target_path: Path | None = None


def _git_toplevel(start: Path) -> Path | None:
    """Return the git checkout root containing *start*, or ``None``."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    root_raw = result.stdout.strip()
    if not root_raw:
        return None
    return Path(root_raw).resolve()


def _is_wp_workspace_checkout(checkout_root: Path, main_repo_root: Path) -> bool:
    """Return ``True`` when checkout is under ``<main>/.worktrees``."""
    wp_root = (main_repo_root / ".worktrees").resolve()
    try:
        checkout_root.resolve().relative_to(wp_root)
        return True
    except ValueError:
        return False


def _resolved_symlink_target(link_path: Path) -> Path | None:
    """Resolve symlink target path without requiring existence."""
    try:
        raw_target = os.readlink(link_path)
    except OSError:
        return None

    candidate = Path(raw_target)
    if not candidate.is_absolute():
        candidate = link_path.parent / candidate
    return candidate.resolve()


def ensure_parallel_checkout_specs_link(start: Path | None = None) -> SpecsLinkResult:
    """Ensure parallel checkout has ``kitty-specs`` symlink to canonical storage.

    Safety rules:
    - Do nothing in the main repository checkout.
    - Do nothing in managed WP workspaces under ``.worktrees/``.
    - Do nothing for legacy repos without ``spec_storage`` config.
    - Never overwrite a non-symlink ``kitty-specs`` path.
    """
    current = (start or Path.cwd()).resolve()

    checkout_root = _git_toplevel(current)
    if checkout_root is None:
        return SpecsLinkResult(status="not_git")

    main_repo_root = get_main_repo_root(checkout_root)
    if checkout_root == main_repo_root:
        return SpecsLinkResult(
            status="main_checkout",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
        )

    if _is_wp_workspace_checkout(checkout_root, main_repo_root):
        return SpecsLinkResult(
            status="wp_workspace",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
        )

    if not (main_repo_root / ".kittify").is_dir():
        return SpecsLinkResult(
            status="not_spec_kitty",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
        )

    if not has_spec_storage_config(main_repo_root):
        return SpecsLinkResult(
            status="legacy_layout",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
        )

    target_path = ensure_spec_storage_ready(main_repo_root)
    if target_path is None:
        logger.debug("spec storage not ready for %s", main_repo_root)
        return SpecsLinkResult(
            status="spec_storage_unavailable",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
        )

    target_path = target_path.resolve()
    link_path = checkout_root / "kitty-specs"

    if target_path == link_path:
        return SpecsLinkResult(
            status="self_target",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
            link_path=link_path,
            target_path=target_path,
        )

    repaired = False

    if link_path.is_symlink():
        current_target = _resolved_symlink_target(link_path)
        if current_target == target_path and link_path.exists():
            return SpecsLinkResult(
                status="already_linked",
                checkout_root=checkout_root,
                main_repo_root=main_repo_root,
                link_path=link_path,
                target_path=target_path,
            )

        link_path.unlink()
        repaired = True
    elif link_path.exists():
        return SpecsLinkResult(
            status="conflict_existing_path",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
            link_path=link_path,
            target_path=target_path,
        )

    relative_target = Path(os.path.relpath(target_path, start=checkout_root))

    try:
        link_path.symlink_to(relative_target, target_is_directory=True)
    except OSError:
        return SpecsLinkResult(
            status="symlink_failed",
            checkout_root=checkout_root,
            main_repo_root=main_repo_root,
            link_path=link_path,
            target_path=target_path,
        )

    return SpecsLinkResult(
        status="repaired" if repaired else "linked",
        checkout_root=checkout_root,
        main_repo_root=main_repo_root,
        link_path=link_path,
        target_path=target_path,
    )


__all__ = ["SpecsLinkResult", "ensure_parallel_checkout_specs_link"]
