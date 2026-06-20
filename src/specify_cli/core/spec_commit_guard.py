"""Guarded commit context for planning/spec artifacts.

This module centralizes commit-repo + branch resolution for writes under
``kitty-specs/`` (including spec-storage orphan-branch worktrees and nested
git repos such as submodules).
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from specify_cli.core.git_ops import get_current_branch, is_git_repo, resolve_primary_branch
from specify_cli.core.spec_artifact_resolver import (
    resolve_feature_dir,
    resolve_spec_artifact_root,
)
from specify_cli.core.spec_storage_config import (
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
)

logger = logging.getLogger(__name__)


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


def _branch_exists(repo_root: Path, branch_name: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=repo_root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _rev_parse(repo_root: Path, rev: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", rev],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _fast_forward_detached_target_if_safe(context: SpecCommitContext) -> None:
    if context.branch_source not in {
        "spec_storage",
        "worktree_detached",
        "worktree_detached_guess",
    }:
        return

    repo_root = context.commit_repo_root
    target_branch = context.target_branch
    head = _rev_parse(repo_root, "HEAD")
    target = _rev_parse(repo_root, target_branch)
    if not head or not target or head == target:
        return

    if _is_ancestor(repo_root, target_branch, "HEAD"):
        update_result = subprocess.run(
            ["git", "branch", "--force", target_branch, "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if update_result.returncode != 0:
            raise RuntimeError(
                f"Could not advance detached spec branch '{target_branch}' to HEAD: "
                f"{update_result.stderr or update_result.stdout}"
            )
        return

    if _is_ancestor(repo_root, "HEAD", target_branch):
        return

    raise RuntimeError(
        f"Detached HEAD in {repo_root} diverges from '{target_branch}'. "
        "Create a branch for the detached commits or reconcile manually, then retry."
    )


def _detached_worktree_context(
    repo_root: Path,
    *,
    main_repo_root: Path | None = None,
    feature_slug: str | None = None,
) -> SpecCommitContext | None:
    """Resolve the target branch for a detached spec worktree.

    Precedence (most explicit first) — guards against the long-standing
    ambiguity where the worktree directory name and the orphan branch name
    might diverge:

    1. ``spec_storage.branch_name`` from ``.kittify/config.yaml`` when
       ``main_repo_root`` is provided and the config is present.  This is
       the only fully unambiguous source.
    2. ``upstream_branch`` / ``target_branch`` from the feature's
       ``meta.json`` when ``main_repo_root`` and ``feature_slug`` are both
       provided.
    3. The directory name as a last-resort guess.  When this branch is
       chosen, ``branch_source`` becomes ``"worktree_detached_guess"`` so
       callers (and tests) can distinguish a confirmed match from a
       heuristic one and emit a warning.

    Returns ``None`` only if none of the three candidates resolves to an
    existing branch.
    """
    if main_repo_root is not None:
        # 1. spec_storage.branch_name (explicit config) — unambiguous.
        try:
            if has_spec_storage_config(main_repo_root):
                config = load_spec_storage_config(main_repo_root)
                if _branch_exists(repo_root, config.branch_name):
                    return SpecCommitContext(
                        commit_repo_root=repo_root,
                        target_branch=config.branch_name,
                        branch_source="worktree_detached",
                    )
        except Exception:
            pass

        # 2. feature meta.json (upstream_branch then target_branch).
        if feature_slug:
            feature_dir = resolve_feature_dir(
                main_repo_root, feature_slug, require_healthy=False
            )
            meta_branch = _read_feature_meta_branch(feature_dir)
            if meta_branch and _branch_exists(repo_root, meta_branch):
                return SpecCommitContext(
                    commit_repo_root=repo_root,
                    target_branch=meta_branch,
                    branch_source="worktree_detached",
                )

    # 3. Directory-name fallback — a heuristic, marked as such.
    branch_guess = repo_root.name
    if _branch_exists(repo_root, branch_guess):
        return SpecCommitContext(
            commit_repo_root=repo_root,
            target_branch=branch_guess,
            branch_source="worktree_detached_guess",
        )
    return None


def _configured_spec_storage_context(
    main_repo_root: Path,
    *,
    probes: list[Path] | None = None,
    commit_repo_root: Path | None = None,
) -> SpecCommitContext | None:
    """Return configured spec-storage commit context when applicable."""
    if not has_spec_storage_config(main_repo_root):
        return None

    try:
        config = load_spec_storage_config(main_repo_root)
        spec_worktree_root = get_spec_worktree_abs_path(main_repo_root, config)
        if not spec_worktree_root.exists():
            return None

        wt_repo = _resolve_git_toplevel(spec_worktree_root, main_repo_root)
        if wt_repo.resolve() != spec_worktree_root.resolve():
            return None

        if (
            commit_repo_root is not None
            and commit_repo_root.resolve() == wt_repo.resolve()
        ):
            return SpecCommitContext(
                commit_repo_root=wt_repo,
                target_branch=config.branch_name,
                branch_source="spec_storage",
            )

        if probes is not None and any(
            _is_relative_to(probe, wt_repo) for probe in probes
        ):
            return SpecCommitContext(
                commit_repo_root=wt_repo,
                target_branch=config.branch_name,
                branch_source="spec_storage",
            )

        if probes is None and commit_repo_root is None:
            return SpecCommitContext(
                commit_repo_root=wt_repo,
                target_branch=config.branch_name,
                branch_source="spec_storage",
            )
    except Exception:
        return None

    return None


def _ensure_branch_exists_for_context(
    repo_root: Path,
    target_branch: str,
    branch_source: str,
) -> None:
    if _branch_exists(repo_root, target_branch):
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
    if current_branch is None:
        _fast_forward_detached_target_if_safe(context)

    checkout_result = subprocess.run(
        ["git", "checkout", target_branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if checkout_result.returncode != 0:
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        dirty_hint = ""
        if status_result.returncode == 0 and status_result.stdout.strip():
            dirty_hint = (
                f" Worktree has uncommitted changes in {repo_root}; "
                "commit or stash them, then retry."
            )
        raise RuntimeError(
            f"Could not checkout target branch '{target_branch}': "
            f"{checkout_result.stderr or checkout_result.stdout}{dirty_hint}"
        )


def to_repo_relative_path(path: Path, repo_root: Path) -> str:
    """Return ``path`` as repo-relative string when possible."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def resolve_specs_repo_and_branch(
    main_repo_root: Path,
    feature_slug: str | None = None,
) -> SpecCommitContext:
    """Resolve which repo and branch to commit kitty-specs changes to.

    This is the single source of truth for worktree-aware commit routing.
    All commands that commit spec/task artifacts should use this function
    (or ``prepare_specs_commit_context`` which delegates here).

    Resolution precedence:

    1. **spec_storage config** – explicit orphan-branch setup in
       ``.kittify/config.yaml``.  ``branch_source="spec_storage"``.
    2. **Worktree detected** – ``kitty-specs/`` resolves to a different git
       repository (e.g. a ``git worktree add`` checkout).  Use that repo's
       root and its current branch.  ``branch_source="worktree_detected"``.
       If the worktree is detached but has a branch matching its directory
       name, use that branch and let commit preparation reattach it.
    3. **feature meta.json** – ``upstream_branch`` (v0.15.0+) or
       ``target_branch`` (legacy).  ``branch_source="feature_meta"``.
    4. **Current branch** – fallback to the current branch on
       ``main_repo_root``.  ``branch_source="current_branch"``.

    When ``commit_repo_root`` differs from ``main_repo_root``, callers should
    not checkout the main repo.  Prepare the returned commit repo before writing.
    """
    # Resolve the spec root via the centralized resolver so commit routing
    # agrees with read routing: this follows a ``kitty-specs`` symlink and, in
    # a split layout, selects the sibling ``spec-kitty/`` that actually holds
    # the feature (instead of a stale committed ``kitty-specs/``).
    kitty_specs_dir = resolve_spec_artifact_root(
        main_repo_root, require_healthy=False, feature_slug=feature_slug
    )

    spec_storage_context = _configured_spec_storage_context(main_repo_root)
    if spec_storage_context is not None:
        return spec_storage_context

    # --- Case 1: kitty-specs is a separate git repo (worktree / submodule) ---
    if kitty_specs_dir.exists():
        specs_repo_root = _resolve_git_toplevel(kitty_specs_dir, main_repo_root)
        if specs_repo_root.resolve() != main_repo_root.resolve():
            specs_branch = get_current_branch(specs_repo_root)
            if specs_branch:
                return SpecCommitContext(
                    commit_repo_root=specs_repo_root,
                    target_branch=specs_branch,
                    branch_source="worktree_detected",
                )
            detached_context = _detached_worktree_context(
                specs_repo_root,
                main_repo_root=main_repo_root,
                feature_slug=feature_slug,
            )
            if detached_context is not None:
                if detached_context.branch_source == "worktree_detached_guess":
                    logger.warning(
                        "Detached spec worktree at %s — falling back to "
                        "directory-name guess %r.  Configure "
                        "spec_storage.branch_name in .kittify/config.yaml "
                        "to make this unambiguous.",
                        specs_repo_root,
                        detached_context.target_branch,
                    )
                return detached_context
            raise RuntimeError(
                f"kitty-specs worktree at {specs_repo_root} is in detached HEAD state. "
                "Checkout a branch before continuing."
            )

    # --- Case 2: spec_storage config (explicit orphan branch setup) ---
    if has_spec_storage_config(main_repo_root):
        try:
            config = load_spec_storage_config(main_repo_root)
            spec_worktree_root = get_spec_worktree_abs_path(main_repo_root, config)

            if spec_worktree_root.exists():
                wt_repo = _resolve_git_toplevel(spec_worktree_root, main_repo_root)
                if wt_repo.resolve() == spec_worktree_root.resolve():
                    return SpecCommitContext(
                        commit_repo_root=spec_worktree_root,
                        target_branch=config.branch_name,
                        branch_source="spec_storage",
                    )
        except Exception:
            pass

    # --- Case 3: feature meta.json upstream_branch / target_branch ---
    if feature_slug:
        feature_dir = kitty_specs_dir / feature_slug
        branch_from_meta = _read_feature_meta_branch(feature_dir)
        if branch_from_meta:
            return SpecCommitContext(
                commit_repo_root=main_repo_root,
                target_branch=branch_from_meta,
                branch_source="feature_meta",
            )

    # --- Case 4: current branch fallback ---
    current = get_current_branch(main_repo_root) or "main"
    return SpecCommitContext(
        commit_repo_root=main_repo_root,
        target_branch=current,
        branch_source="current_branch",
    )


def prepare_specs_commit_context(
    main_repo_root: Path,
    *,
    tracked_paths: list[Path],
    feature_dir: Path | None = None,
    fallback_branch: str | None = None,
) -> SpecCommitContext:
    """Resolve and prepare commit context for ``kitty-specs`` writes.

    This is a higher-level wrapper around ``resolve_specs_repo_and_branch``
    that also handles per-file anchor resolution, explicit fallback branches,
    and ensures the resolved branch is checked out.

    Branch resolution precedence:
    1. Worktree detection (``kitty-specs/`` is a separate git repo)
    2. ``spec_storage.branch_name`` when tracked paths are under spec worktree
    3. feature ``meta.json`` (``upstream_branch`` then ``target_branch``)
    4. explicit ``fallback_branch``
    5. current branch in commit repo (or ``main``)
    """
    if not tracked_paths and feature_dir is None:
        tracked_paths = [main_repo_root / "kitty-specs"]

    anchor = tracked_paths[0] if tracked_paths else feature_dir
    if anchor is None:
        anchor = main_repo_root

    commit_repo_root = _resolve_git_toplevel(anchor, main_repo_root)

    probes = tracked_paths[:] if tracked_paths else [anchor]
    if feature_dir is not None:
        probes.append(feature_dir)

    spec_storage_context = _configured_spec_storage_context(
        main_repo_root,
        probes=probes,
        commit_repo_root=commit_repo_root,
    )
    if spec_storage_context is not None:
        ensure_branch_checked_out(spec_storage_context)
        return spec_storage_context

    # --- Worktree detection (Case 1): if anchor resolves to a different
    # git repo, commit there on its current branch.  No checkout needed. ---
    if commit_repo_root.resolve() != main_repo_root.resolve():
        specs_branch = get_current_branch(commit_repo_root)
        if specs_branch:
            return SpecCommitContext(
                commit_repo_root=commit_repo_root,
                target_branch=specs_branch,
                branch_source="worktree_detected",
            )
        # Pass main_repo_root + the feature slug (derived from feature_dir
        # when callers supplied one) so the detached-HEAD case can prefer
        # spec_storage.branch_name / meta.json over the directory-name
        # guess.
        feature_slug_hint = feature_dir.name if feature_dir is not None else None
        detached_context = _detached_worktree_context(
            commit_repo_root,
            main_repo_root=main_repo_root,
            feature_slug=feature_slug_hint,
        )
        if detached_context is not None:
            if detached_context.branch_source == "worktree_detached_guess":
                logger.warning(
                    "Detached spec worktree at %s — falling back to "
                    "directory-name guess %r.  Configure "
                    "spec_storage.branch_name in .kittify/config.yaml "
                    "to make this unambiguous.",
                    commit_repo_root,
                    detached_context.target_branch,
                )
            ensure_branch_checked_out(detached_context)
            return detached_context
        raise RuntimeError(
            f"Spec worktree at {commit_repo_root} is in detached HEAD state. "
            "Checkout a branch before continuing."
        )

    target_branch: str | None = None
    branch_source = "current_branch"

    if has_spec_storage_config(main_repo_root):
        try:
            config = load_spec_storage_config(main_repo_root)
            spec_worktree_root = get_spec_worktree_abs_path(main_repo_root, config)
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
    "resolve_specs_repo_and_branch",
    "to_repo_relative_path",
]
