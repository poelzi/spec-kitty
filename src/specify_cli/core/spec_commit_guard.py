"""Guarded commit context for planning/spec artifacts.

This module centralizes commit-repo + branch resolution for writes under
``kitty-specs/`` (including spec-storage orphan-branch worktrees and nested
git repos such as submodules).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from specify_cli.core.git_ops import get_current_branch, is_git_repo, resolve_primary_branch
from specify_cli.core.spec_storage_config import (
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
)


@dataclass
class SpecCommitContext:
    """Resolved commit context for planning/spec artifacts."""

    commit_repo_root: Path
    target_branch: str
    branch_source: str


def _resolve_git_toplevel(path: Path, fallback: Path) -> Path:
    probe_dir = path if path.is_dir() else path.parent
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=probe_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return fallback.resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _read_feature_meta_branch(feature_dir: Path | None) -> str | None:
    if feature_dir is None:
        return None

    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    branch = meta.get("upstream_branch") or meta.get("target_branch")
    if isinstance(branch, str) and branch.strip():
        return branch.strip()
    return None


def _ensure_branch_exists_for_context(
    repo_root: Path,
    target_branch: str,
    branch_source: str,
) -> None:
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", target_branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    ).returncode == 0

    if exists:
        return

    if branch_source == "spec_storage":
        raise RuntimeError(
            f"Spec storage branch '{target_branch}' not found in {repo_root}. "
            "Run 'spec-kitty init' to repair orphan-branch setup."
        )

    if target_branch in {"main", "master"}:
        raise RuntimeError(
            f"Target branch '{target_branch}' not found in {repo_root}."
        )

    primary_branch = resolve_primary_branch(repo_root)
    create_result = subprocess.run(
        ["git", "branch", target_branch, primary_branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if create_result.returncode != 0:
        raise RuntimeError(
            f"Could not create target branch '{target_branch}': "
            f"{create_result.stderr or create_result.stdout}"
        )


def ensure_branch_checked_out(context: SpecCommitContext) -> None:
    """Ensure commit repository is checked out to the resolved target branch."""
    repo_root = context.commit_repo_root
    target_branch = context.target_branch

    if not is_git_repo(repo_root):
        raise RuntimeError(f"Not in a git repository: {repo_root}")

    current_branch = get_current_branch(repo_root)
    if current_branch == target_branch:
        return

    _ensure_branch_exists_for_context(repo_root, target_branch, context.branch_source)

    checkout_result = subprocess.run(
        ["git", "checkout", target_branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if checkout_result.returncode != 0:
        raise RuntimeError(
            f"Could not checkout target branch '{target_branch}': "
            f"{checkout_result.stderr or checkout_result.stdout}"
        )


def to_repo_relative_path(path: Path, repo_root: Path) -> str:
    """Return ``path`` as repo-relative string when possible."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def prepare_specs_commit_context(
    main_repo_root: Path,
    *,
    tracked_paths: list[Path],
    feature_dir: Path | None = None,
    fallback_branch: str | None = None,
) -> SpecCommitContext:
    """Resolve and prepare commit context for ``kitty-specs`` writes.

    Branch resolution precedence:
    1. ``spec_storage.branch_name`` when tracked paths are under spec worktree
    2. feature ``meta.json`` (`upstream_branch` then `target_branch`)
    3. explicit ``fallback_branch``
    4. current branch in commit repo (or ``main``)
    """
    if not tracked_paths and feature_dir is None:
        tracked_paths = [main_repo_root / "kitty-specs"]

    anchor = tracked_paths[0] if tracked_paths else feature_dir
    if anchor is None:
        anchor = main_repo_root

    commit_repo_root = _resolve_git_toplevel(anchor, main_repo_root)

    target_branch: str | None = None
    branch_source = "current_branch"

    if has_spec_storage_config(main_repo_root):
        try:
            config = load_spec_storage_config(main_repo_root)
            spec_worktree_root = get_spec_worktree_abs_path(main_repo_root, config)
            probes = tracked_paths[:] if tracked_paths else [anchor]
            if feature_dir is not None:
                probes.append(feature_dir)

            if commit_repo_root.resolve() == spec_worktree_root.resolve() or any(
                _is_relative_to(probe, spec_worktree_root) for probe in probes
            ):
                target_branch = config.branch_name
                branch_source = "spec_storage"
        except Exception:
            # Fall back to feature metadata / current branch.
            pass

    if target_branch is None:
        branch_from_meta = _read_feature_meta_branch(feature_dir)
        if branch_from_meta:
            target_branch = branch_from_meta
            branch_source = "feature_meta"

    if target_branch is None and fallback_branch:
        target_branch = fallback_branch
        branch_source = "fallback"

    if target_branch is None:
        target_branch = get_current_branch(commit_repo_root) or "main"
        branch_source = "current_branch"

    context = SpecCommitContext(
        commit_repo_root=commit_repo_root,
        target_branch=target_branch,
        branch_source=branch_source,
    )
    ensure_branch_checked_out(context)
    return context


__all__ = [
    "SpecCommitContext",
    "ensure_branch_checked_out",
    "prepare_specs_commit_context",
    "to_repo_relative_path",
]
