"""Centralized spec artifact root resolver.

Routes all planning artifact read/write paths to the correct location:
- For repos with ``spec_storage`` config → spec worktree checkout path
- For legacy repos (no ``spec_storage`` config) → ``repo_root / "kitty-specs"``

This module is the single seam for all commands that create or modify
planning artifacts (specs, plans, work packages, meta.json).

Key design decisions:
- Backward compatibility: Legacy repos without spec_storage config get
  ``repo_root / "kitty-specs"`` transparently.
- Health validation: When ``require_healthy=True`` (default), the resolver
  verifies the spec worktree is in a healthy state before returning paths.
- Consistent API: ``resolve_spec_artifact_root()``, ``resolve_feature_dir()``,
  and ``resolve_tasks_dir()`` provide progressively specific path resolution.
"""

from __future__ import annotations

import logging
from pathlib import Path

from specify_cli.core.spec_storage_config import (
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
)
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    discover_spec_worktree,
)

logger = logging.getLogger(__name__)


class SpecArtifactResolutionError(RuntimeError):
    """Raised when the spec artifact root cannot be resolved."""


def resolve_spec_artifact_root(
    repo_root: Path,
    *,
    require_healthy: bool = True,
) -> Path:
    """Return the absolute path to the spec artifact root.

    For repos with ``spec_storage`` config, this is the worktree checkout
    directory.  For legacy repos, this is ``repo_root / "kitty-specs"``.

    Args:
        repo_root: Main repository root directory.
        require_healthy: If ``True`` (default), validate worktree health
            before returning.  Raises ``SpecArtifactResolutionError`` if
            the worktree is unhealthy.

    Returns:
        Absolute path to the spec artifact root directory.

    Raises:
        SpecArtifactResolutionError: If ``require_healthy=True`` and the
            spec worktree is not in a healthy state.
    """
    if not has_spec_storage_config(repo_root):
        # Legacy repo — use repo_root / "kitty-specs"
        legacy_path = repo_root / "kitty-specs"
        logger.debug(
            "No spec_storage config; using legacy path: %s", legacy_path
        )
        return legacy_path

    config = load_spec_storage_config(repo_root)
    worktree_abs = get_spec_worktree_abs_path(repo_root, config)

    if require_healthy:
        wt_state = discover_spec_worktree(repo_root, config)
        if wt_state.health_status != HEALTH_HEALTHY:
            raise SpecArtifactResolutionError(
                f"Spec worktree at '{worktree_abs}' is not healthy "
                f"(status: {wt_state.health_status}).  "
                f"Run 'spec-kitty init' to repair, or use "
                f"--require-healthy=false to bypass."
            )

    logger.debug("Resolved spec artifact root: %s", worktree_abs)
    return worktree_abs


def resolve_feature_dir(
    repo_root: Path,
    feature_slug: str,
    *,
    require_healthy: bool = True,
) -> Path:
    """Return path to a specific feature directory under spec artifact root.

    Args:
        repo_root: Main repository root directory.
        feature_slug: Feature slug (e.g., ``"001-my-feature"``).
        require_healthy: If ``True``, validate worktree health.

    Returns:
        Absolute path to the feature directory.

    Raises:
        SpecArtifactResolutionError: If health check fails.
    """
    artifact_root = resolve_spec_artifact_root(
        repo_root, require_healthy=require_healthy
    )
    return artifact_root / feature_slug


def resolve_tasks_dir(
    repo_root: Path,
    feature_slug: str,
    *,
    require_healthy: bool = True,
) -> Path:
    """Return path to tasks directory for a feature.

    Args:
        repo_root: Main repository root directory.
        feature_slug: Feature slug (e.g., ``"001-my-feature"``).
        require_healthy: If ``True``, validate worktree health.

    Returns:
        Absolute path to the feature's tasks directory.

    Raises:
        SpecArtifactResolutionError: If health check fails.
    """
    feature_dir = resolve_feature_dir(
        repo_root, feature_slug, require_healthy=require_healthy
    )
    return feature_dir / "tasks"


__all__ = [
    "SpecArtifactResolutionError",
    "resolve_feature_dir",
    "resolve_spec_artifact_root",
    "resolve_tasks_dir",
]
