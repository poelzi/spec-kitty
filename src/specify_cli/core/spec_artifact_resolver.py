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
import os
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

# Environment escape hatch: when set, forces the spec artifact root for repos
# that have no ``spec_storage`` config (e.g. a workflow sandbox where the real
# specs are mounted at a non-standard path). Honored ahead of the legacy
# ``kitty-specs`` heuristic. Empty/unset is ignored.
SPECS_ROOT_ENV = "SPEC_KITTY_SPECS_ROOT"

# Legacy candidate directory names, in preference order. ``kitty-specs`` is the
# canonical location; ``spec-kitty`` is the path some workflow mounts use when
# the real specs are kept separate from a stale committed ``kitty-specs/``.
_LEGACY_CANDIDATES = ("kitty-specs", "spec-kitty")


def _safe_resolve(path: Path) -> Path:
    """``Path.resolve()`` that never raises (so symlinks are followed but a
    missing/cyclic path degrades to a normalized absolute path)."""
    try:
        return path.resolve()
    except OSError:
        return path


def _contains_feature(candidate: Path, feature_slug: str | None) -> bool:
    if not feature_slug:
        return False
    try:
        return (candidate / feature_slug).is_dir()
    except OSError:
        return False


def _resolve_legacy_specs_root(
    repo_root: Path, feature_slug: str | None
) -> Path:
    """Resolve the spec root for a legacy repo (no ``spec_storage`` config).

    Robust to: a ``kitty-specs`` symlink (followed), and a *split* layout where
    the canonical ``kitty-specs`` is a stale committed directory while the real
    specs live in a sibling ``spec-kitty/`` (the failure mode that stranded
    dependent WPs). Resolution order:

    1. ``$SPEC_KITTY_SPECS_ROOT`` env override, if set.
    2. When ``feature_slug`` is given, the first candidate that actually
       CONTAINS that feature (so a stale tree lacking the feature is skipped).
    3. The first candidate that exists on disk.
    4. ``kitty-specs`` (resolved) as the backward-compatible default.
    """
    env_override = os.environ.get(SPECS_ROOT_ENV)
    if env_override:
        return _safe_resolve(Path(env_override).expanduser())

    candidates = [repo_root / name for name in _LEGACY_CANDIDATES]

    if feature_slug:
        for cand in candidates:
            if _contains_feature(cand, feature_slug):
                return _safe_resolve(cand)

    for cand in candidates:
        try:
            if cand.exists():
                return _safe_resolve(cand)
        except OSError:
            continue

    return _safe_resolve(repo_root / "kitty-specs")


class SpecArtifactResolutionError(RuntimeError):
    """Raised when the spec artifact root cannot be resolved."""


def resolve_spec_artifact_root(
    repo_root: Path,
    *,
    require_healthy: bool = True,
    feature_slug: str | None = None,
) -> Path:
    """Return the absolute path to the spec artifact root.

    For repos with ``spec_storage`` config, this is the worktree checkout
    directory.  For legacy repos, this is ``repo_root / "kitty-specs"``.

    Args:
        repo_root: Main repository root directory.
        require_healthy: If ``True`` (default), validate worktree health
            before returning.  Raises ``SpecArtifactResolutionError`` if
            the worktree is unhealthy.
        feature_slug: Optional feature slug. When given, legacy resolution
            prefers the candidate spec root that actually contains the
            feature (handles a split layout where a stale ``kitty-specs/``
            shadows the real specs in a sibling ``spec-kitty/``).

    Returns:
        Absolute path to the spec artifact root directory.

    Raises:
        SpecArtifactResolutionError: If ``require_healthy=True`` and the
            spec worktree is not in a healthy state.
    """
    if not has_spec_storage_config(repo_root):
        # Legacy repo — resolve robustly (symlink/split/env aware).
        legacy_path = _resolve_legacy_specs_root(repo_root, feature_slug)
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
        repo_root, require_healthy=require_healthy, feature_slug=feature_slug
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
