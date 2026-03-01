"""Spec commit policy: manual-edit detection, commit, and auto-push.

Provides policy enforcement for committing planning artifacts on the
spec branch.  Key capabilities:

- **Manual-edit detection**: Identifies files changed in the spec worktree
  that were not part of the intended operation (e.g., user hand-edits).
- **Commit with policy**: Commits intended files, with
  include/skip/abort decisions for manually edited files.
- **Auto-push**: Optional push after successful commit (config-driven,
  default off; never force-pushes).

This module is designed for use by future WPs that wire commit flows
into specific commands.  The API is stable and testable in isolation.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


MANUAL_EDIT_POLICY_ENV = "SPEC_KITTY_MANUAL_EDIT_POLICY"
DEFAULT_MANUAL_EDIT_POLICY = "skip"
VALID_MANUAL_EDIT_POLICIES = {"include", "skip", "abort"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SpecCommitAction:
    """Result of commit policy evaluation.

    Attributes:
        action: The decided action — ``"include"``, ``"skip"``, or ``"abort"``.
        intended_files: Files that the command intended to modify.
        manual_files: Files changed in the worktree but *not* in the
            intended list (potential manual edits).
    """

    action: str  # "include" | "skip" | "abort"
    intended_files: list[str] = field(default_factory=list)
    manual_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Manual-edit detection
# ---------------------------------------------------------------------------


def detect_manual_edits(
    worktree_path: Path,
    intended_files: list[str],
) -> list[str]:
    """Detect changes in worktree not in the intended_files list.

    Uses ``git status --porcelain`` to enumerate all changed files in the
    worktree, then filters out files that appear in *intended_files*.

    Args:
        worktree_path: Absolute path to the spec worktree.
        intended_files: List of file paths (relative to worktree root)
            that the current operation intends to modify.

    Returns:
        List of file paths (relative to worktree root) that have changes
        but are **not** in the intended list.  Empty list means no
        unexpected edits detected.
    """
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
        logger.warning(
            "git status failed in %s (rc=%d): %s",
            worktree_path,
            result.returncode,
            result.stderr.strip(),
        )
        return []

    # Normalise intended files for comparison (strip leading ./ and trailing /)
    normalised_intended = {
        _normalise_path(f) for f in intended_files
    }

    manual: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Porcelain v1 format: XY <path>  or  XY <path> -> <new_path>
        # The path starts at position 3.
        raw_path = line[3:].strip()
        # Handle renames: "old -> new"
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ")[-1]

        normalised = _normalise_path(raw_path)
        if normalised not in normalised_intended:
            manual.append(raw_path)

    return manual


def _normalise_path(p: str) -> str:
    """Normalise a file path for comparison.

    Strips leading ``./``, removes trailing ``/``, and collapses
    duplicate separators.
    """
    p = p.strip()
    if p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    return p


# ---------------------------------------------------------------------------
# Commit with policy enforcement
# ---------------------------------------------------------------------------


def commit_spec_changes(
    worktree_path: Path,
    intended_files: list[str],
    message: str,
    *,
    include_manual: bool = False,
    auto_push: bool = False,
    remote: str = "origin",
) -> bool:
    """Commit spec changes on the spec branch with policy enforcement.

    Steps:
    1. Stage all *intended_files*.
    2. If ``include_manual`` is ``True``, also stage any manually edited
       files detected in the worktree.
    3. Create a commit with the provided *message*.
    4. If ``auto_push`` is ``True``, push to *remote*.  Failures are
       logged but do **not** corrupt the local commit.

    Args:
        worktree_path: Absolute path to the spec worktree.
        intended_files: List of file paths (relative to worktree root)
            to stage and commit.
        message: Commit message.
        include_manual: If ``True``, also stage manually edited files.
        auto_push: If ``True``, push after successful commit.
        remote: Remote name for push (default ``"origin"``).

    Returns:
        ``True`` if commit succeeded, ``False`` otherwise.
        Push failures return ``True`` (commit is still valid).
    """
    if not worktree_path.is_dir():
        logger.error("Worktree path does not exist: %s", worktree_path)
        return False

    # Determine files to stage
    files_to_stage = list(intended_files)
    if include_manual:
        manual = detect_manual_edits(worktree_path, intended_files)
        files_to_stage.extend(manual)
        if manual:
            logger.info(
                "Including %d manual edit(s) in commit: %s",
                len(manual),
                manual,
            )

    if not files_to_stage:
        logger.info("No files to stage; skipping commit.")
        return True  # Nothing to do is success

    # Stage files
    for file_path in files_to_stage:
        add_result = subprocess.run(
            ["git", "add", file_path],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if add_result.returncode != 0:
            logger.warning(
                "git add failed for '%s': %s",
                file_path,
                add_result.stderr.strip(),
            )
            # Continue staging other files; commit may still succeed.

    # Commit.
    # Use --no-verify because the spec worktree (orphan branch) does not
    # contain .pre-commit-config.yaml and hooks inherited from the parent
    # repo will fail in this context.
    commit_result = subprocess.run(
        ["git", "commit", "--no-verify", "-m", message],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if commit_result.returncode != 0:
        stderr = commit_result.stderr.strip()
        stdout = commit_result.stdout.strip()
        combined = f"{stdout} {stderr}"
        if "nothing to commit" in combined or "nothing added to commit" in combined:
            logger.info("Nothing to commit (files unchanged).")
            return True
        logger.error("git commit failed: %s", combined)
        return False

    logger.info("Committed spec changes: %s", message)

    # Auto-push (best effort — never force push)
    if auto_push:
        _try_push(worktree_path, remote)

    return True


def _try_push(
    worktree_path: Path,
    remote: str = "origin",
) -> bool:
    """Attempt to push the current branch to *remote*.

    Never uses ``--force``.  Returns ``True`` on success, ``False`` on
    failure.  Failures are logged but do not raise.
    """
    # Determine current branch
    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if branch_result.returncode != 0 or not branch_result.stdout.strip():
        logger.warning("Cannot determine current branch for push; skipping.")
        return False

    branch = branch_result.stdout.strip()

    push_result = subprocess.run(
        ["git", "push", remote, branch],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if push_result.returncode != 0:
        logger.warning(
            "Auto-push to %s/%s failed: %s",
            remote,
            branch,
            push_result.stderr.strip(),
        )
        return False

    logger.info("Pushed to %s/%s", remote, branch)
    return True


def resolve_manual_edit_policy(
    worktree_path: Path,
    intended_files: list[str],
    *,
    manual_policy: str | None = None,
    interactive: bool = False,
) -> SpecCommitAction:
    """Determine the manual-edit commit policy.

    In non-interactive mode (the default for agent workflows), policy is
    deterministic and supports explicit override:

    1. ``manual_policy`` argument, if provided.
    2. ``SPEC_KITTY_MANUAL_EDIT_POLICY`` environment variable, if set.
    3. Default ``skip``.

    Valid policy values are ``include``, ``skip``, and ``abort``.

    Non-interactive behavior with no explicit override:

    - No manual edits detected -> ``action="include"`` (commit intended).
    - Manual edits detected -> ``action="skip"`` (commit only intended,
      leave manual edits unstaged so the user can review them).

    In interactive mode, this function prompts the user to choose
    include/skip/abort.

    Args:
        worktree_path: Absolute path to the spec worktree.
        intended_files: Files the current operation intends to modify.
        manual_policy: Optional explicit policy override
            (``include`` | ``skip`` | ``abort``).
        interactive: If ``True`` and no explicit policy override is
            supplied, prompt for include/skip/abort.

    Returns:
        A ``SpecCommitAction`` describing the decided policy.
    """
    manual = detect_manual_edits(worktree_path, intended_files)

    if not manual:
        return SpecCommitAction(
            action="include",
            intended_files=list(intended_files),
            manual_files=[],
        )

    source = "default"
    selected_policy: str | None = None

    if manual_policy is not None:
        normalised = _normalise_policy_value(manual_policy)
        if normalised is None:
            logger.warning(
                "Invalid manual policy argument '%s'; falling back to default '%s'",
                manual_policy,
                DEFAULT_MANUAL_EDIT_POLICY,
            )
        else:
            selected_policy = normalised
            source = "argument"

    if selected_policy is None:
        env_policy = os.environ.get(MANUAL_EDIT_POLICY_ENV)
        if env_policy:
            normalised = _normalise_policy_value(env_policy)
            if normalised is None:
                logger.warning(
                    "Invalid %s value '%s'; falling back to default '%s'",
                    MANUAL_EDIT_POLICY_ENV,
                    env_policy,
                    DEFAULT_MANUAL_EDIT_POLICY,
                )
            else:
                selected_policy = normalised
                source = f"env:{MANUAL_EDIT_POLICY_ENV}"

    if selected_policy is None and interactive:
        selected_policy = _prompt_manual_policy_choice()
        source = "interactive"

    if selected_policy is None:
        selected_policy = DEFAULT_MANUAL_EDIT_POLICY
        source = "default"

    logger.info(
        "Detected %d manual edit(s) in spec worktree, policy=%s (%s): %s",
        len(manual),
        selected_policy,
        source,
        manual,
    )

    return SpecCommitAction(
        action=selected_policy,
        intended_files=list(intended_files),
        manual_files=manual,
    )


def _normalise_policy_value(policy: str) -> str | None:
    """Normalise and validate a manual-edit policy value."""
    value = policy.strip().lower()
    if value in VALID_MANUAL_EDIT_POLICIES:
        return value
    return None


def _prompt_manual_policy_choice() -> str:
    """Prompt user to choose include/skip/abort for manual edits."""
    prompt = "Manual edits detected. Choose [i]nclude/[s]kip/[a]bort: "
    choices = {
        "i": "include",
        "include": "include",
        "s": "skip",
        "skip": "skip",
        "a": "abort",
        "abort": "abort",
    }

    while True:
        try:
            raw = input(prompt).strip().lower()
        except EOFError:
            logger.warning(
                "Input unavailable during interactive manual-edit prompt; "
                "defaulting to '%s'",
                DEFAULT_MANUAL_EDIT_POLICY,
            )
            return DEFAULT_MANUAL_EDIT_POLICY

        if raw in choices:
            return choices[raw]

        print("Please enter include, skip, or abort.")


def commit_with_policy(
    worktree_path: Path,
    intended_files: list[str],
    message: str,
    *,
    manual_policy: str | None = None,
    auto_push: bool = False,
    remote: str = "origin",
    interactive: bool = False,
) -> tuple[bool, SpecCommitAction]:
    """Evaluate manual-edit policy then commit.

    Convenience wrapper that combines ``resolve_manual_edit_policy`` +
    ``commit_spec_changes`` into a single call that honours the policy:

    - ``action="include"`` -> commit intended + manual files.
    - ``action="skip"`` -> commit only intended files.
    - ``action="abort"`` -> skip commit entirely.

    Args:
        worktree_path: Absolute path to the spec worktree.
        intended_files: Files the current operation intends to modify.
        message: Commit message.
        manual_policy: Optional explicit policy override
            (``include`` | ``skip`` | ``abort``).
        auto_push: Whether to push after commit.
        remote: Remote name for push.
        interactive: If ``True``, interactive manual-edit prompt
            when no explicit policy is provided.

    Returns:
        ``(ok, action)`` tuple — ``ok`` is ``True`` if commit succeeded.
        ``ok`` is ``False`` when policy is ``abort`` or commit failed.
    """
    action = resolve_manual_edit_policy(
        worktree_path,
        intended_files,
        manual_policy=manual_policy,
        interactive=interactive,
    )

    if action.action == "abort":
        logger.info("Manual-edit policy: abort — skipping commit.")
        return False, action

    include_manual = action.action == "include" and bool(action.manual_files)
    ok = commit_spec_changes(
        worktree_path=worktree_path,
        intended_files=intended_files,
        message=message,
        include_manual=include_manual,
        auto_push=auto_push,
        remote=remote,
    )
    return ok, action


__all__ = [
    "DEFAULT_MANUAL_EDIT_POLICY",
    "MANUAL_EDIT_POLICY_ENV",
    "SpecCommitAction",
    "commit_spec_changes",
    "commit_with_policy",
    "detect_manual_edits",
    "resolve_manual_edit_policy",
]
