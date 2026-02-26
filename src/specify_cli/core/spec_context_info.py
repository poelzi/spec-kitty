"""Spec storage context information for agent context outputs.

Exposes spec worktree branch, path, and health information so that
agent context files and CLI commands can display the current spec
storage topology.

Key design decisions:
- Pure data-gathering functions — no side effects.
- Graceful degradation when ``spec_storage`` is not configured.
- Returns typed dataclass for structured consumption.
- Backward-compatible: legacy repos get ``configured=False`` with
  sensible defaults.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_MISSING_REGISTRATION,
    SpecWorktreeState,
    discover_spec_worktree,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SpecStorageContextInfo:
    """Spec storage information suitable for context output.

    Attributes:
        configured: Whether ``spec_storage`` is configured in the
            project (``False`` for legacy repos).
        branch_name: Configured branch name (or default).
        worktree_path: Absolute resolved path to the spec worktree.
        health_status: Current worktree health from discovery
            (e.g. ``"healthy"``, ``"missing_path"``).
            ``None`` when discovery was not performed.
    """

    configured: bool
    branch_name: str
    worktree_path: Optional[str]
    health_status: Optional[str]

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON output."""
        return {
            "configured": self.configured,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "health_status": self.health_status,
        }


# ---------------------------------------------------------------------------
# Context info builder
# ---------------------------------------------------------------------------


def get_spec_storage_context_info(
    repo_root: Path,
    *,
    run_discovery: bool = True,
) -> SpecStorageContextInfo:
    """Build spec storage context information for the given repo.

    Args:
        repo_root: Repository root directory.
        run_discovery: If ``True`` (default), perform worktree discovery
            to populate ``health_status``.  Set to ``False`` to skip
            the ``git worktree list`` subprocess call (useful in
            environments where git is not available).

    Returns:
        Populated :class:`SpecStorageContextInfo`.
    """
    configured = has_spec_storage_config(repo_root)

    try:
        config = load_spec_storage_config(repo_root)
    except Exception:
        # If config cannot be loaded, return unconfigured info.
        logger.debug("Could not load spec_storage config for %s", repo_root)
        return SpecStorageContextInfo(
            configured=False,
            branch_name="kitty-specs",
            worktree_path=None,
            health_status=None,
        )

    # Resolve absolute worktree path.
    try:
        abs_path = str(get_spec_worktree_abs_path(repo_root, config))
    except Exception:
        abs_path = None

    # Discover health status.
    health_status: Optional[str] = None
    if run_discovery:
        try:
            state: SpecWorktreeState = discover_spec_worktree(repo_root, config)
            health_status = state.health_status
        except Exception:
            logger.debug(
                "Worktree discovery failed for %s", repo_root, exc_info=True
            )
            health_status = None

    return SpecStorageContextInfo(
        configured=configured,
        branch_name=config.branch_name,
        worktree_path=abs_path,
        health_status=health_status,
    )


__all__ = [
    "SpecStorageContextInfo",
    "get_spec_storage_context_info",
]
