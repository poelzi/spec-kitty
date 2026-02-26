"""Merge safety utilities for spec storage paths.

Prevents stale landing branches from reintroducing spec storage directories
(e.g. ``kitty-specs/``) into main during merge operations.

This module provides building blocks that can be integrated into merge
commands and CI checks.  The exclusion patterns are derived from the
repository's ``spec_storage`` configuration, with a fallback to the
legacy ``kitty-specs`` default.

Key design decisions:
- Pure helper functions — no git subprocess calls.
- Works with or without ``spec_storage`` config (backward-compatible).
- Patterns use ``fnmatch``-style glob matching for easy integration
  with both Python code and git pathspec.
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from specify_cli.core.spec_storage_config import (
    DEFAULT_WORKTREE_PATH,
    SpecStorageConfig,
    has_spec_storage_config,
    load_spec_storage_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exclusion pattern generation
# ---------------------------------------------------------------------------


def get_spec_path_exclusion_patterns(repo_root: Path) -> list[str]:
    """Return git pathspec patterns for excluding spec storage paths from merges.

    Uses configured ``worktree_path``, falls back to ``'kitty-specs'`` for
    legacy repos that do not have a ``spec_storage`` block.

    The returned patterns use a trailing ``/*`` glob to match all files
    beneath the spec storage directory, plus a bare directory pattern to
    catch the directory entry itself.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of pathspec-style exclusion patterns (e.g.
        ``["kitty-specs", "kitty-specs/*"]``).
    """
    if has_spec_storage_config(repo_root):
        config = load_spec_storage_config(repo_root)
        worktree_path = config.worktree_path
    else:
        # Legacy fallback — always exclude the default path.
        worktree_path = DEFAULT_WORKTREE_PATH

    return _build_exclusion_patterns(worktree_path)


def get_spec_path_exclusion_patterns_from_config(
    config: SpecStorageConfig,
) -> list[str]:
    """Return exclusion patterns from an already-loaded config.

    Useful when the caller has already loaded the config and wants to
    avoid a redundant disk read.

    Args:
        config: Pre-loaded spec storage configuration.

    Returns:
        List of pathspec-style exclusion patterns.
    """
    return _build_exclusion_patterns(config.worktree_path)


def _build_exclusion_patterns(worktree_path: str) -> list[str]:
    """Build exclusion pattern list from a worktree path string.

    Normalises the path (strips trailing slashes) and returns both a
    bare directory pattern and a recursive glob pattern.
    """
    # Normalise: strip trailing slashes and backslashes.
    normalised = worktree_path.rstrip("/\\")
    if not normalised:
        normalised = DEFAULT_WORKTREE_PATH

    return [
        normalised,
        f"{normalised}/*",
    ]


# ---------------------------------------------------------------------------
# Path filtering
# ---------------------------------------------------------------------------


def filter_merge_paths(
    paths: list[str],
    exclusion_patterns: list[str],
) -> list[str]:
    """Remove spec storage paths from a list of paths to be merged.

    Each path is checked against every exclusion pattern using
    ``fnmatch``-style matching.  Paths that match any pattern are
    removed from the result.

    Args:
        paths: List of file/directory paths (relative to repo root).
        exclusion_patterns: Patterns from
            :func:`get_spec_path_exclusion_patterns`.

    Returns:
        Filtered list with spec storage paths removed.
    """
    return [
        p for p in paths
        if not should_exclude_from_merge(p, exclusion_patterns)
    ]


def should_exclude_from_merge(
    path: str,
    exclusion_patterns: list[str],
) -> bool:
    """Check if a single path should be excluded from merge.

    Matches against the exclusion patterns using ``fnmatch``.  Also
    performs a prefix check so that deeply nested paths beneath the
    spec storage root are caught even if the glob depth is limited.

    Args:
        path: File path relative to repo root.
        exclusion_patterns: Patterns from
            :func:`get_spec_path_exclusion_patterns`.

    Returns:
        ``True`` if the path should be excluded.
    """
    # Normalise path separators.
    normalised = path.replace("\\", "/").rstrip("/")

    for pattern in exclusion_patterns:
        pat = pattern.replace("\\", "/").rstrip("/")

        # Direct fnmatch.
        if fnmatch.fnmatch(normalised, pat):
            return True

        # Prefix check: if the path starts with the directory pattern
        # followed by a separator, it lives inside the spec storage tree.
        # This catches nested paths like "kitty-specs/001-feat/plan.md"
        # even when the glob is only "kitty-specs/*" (single level).
        base_dir = pat.rstrip("/*")
        if base_dir and (
            normalised == base_dir
            or normalised.startswith(base_dir + "/")
        ):
            return True

    return False


__all__ = [
    "filter_merge_paths",
    "get_spec_path_exclusion_patterns",
    "get_spec_path_exclusion_patterns_from_config",
    "should_exclude_from_merge",
]
