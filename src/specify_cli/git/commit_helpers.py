"""Safe commit helper that preserves staging area.

This module provides utilities for committing only specific files without
capturing unrelated staged changes.

Optional defence-in-depth: pass ``expected_branch`` and / or
``expected_parent_oid`` to detect concurrent modifications to the worktree
between context resolution and the commit (e.g. a manual ``git checkout``
landing on the wrong branch).  When the precondition fails, the staged
files are NOT committed and the caller learns about the race instead of
silently producing a misplaced commit.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _current_branch(repo_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def safe_commit(
    repo_path: Path,
    files_to_commit: list[Path],
    commit_message: str,
    allow_empty: bool = False,
    no_verify: bool = False,
    *,
    expected_branch: str | None = None,
    expected_parent_oid: str | None = None,
) -> bool:
    """Commit only specified files, preserving existing staging area.

    This function ensures that only the explicitly provided files are committed,
    preventing unrelated staged files from being accidentally included in the commit.

    Strategy:
    1. Save current staging area state (git stash)
    2. Stage only the intended files
    3. Commit those files
    4. Restore original staging area (git stash pop)

    Args:
        repo_path: Path to the git repository root
        files_to_commit: List of file paths to commit (absolute or relative to repo_path)
        commit_message: The commit message to use
        allow_empty: If True, return success even if there's nothing to commit
        no_verify: If True, pass --no-verify to skip pre-commit hooks
        expected_branch: If set, verify ``git symbolic-ref HEAD`` matches BEFORE
            staging.  Mismatch returns ``False`` without staging or committing
            so the caller can surface the race rather than silently producing
            a misplaced commit.  Pass the resolved branch from your
            :class:`SpecCommitContext` here.
        expected_parent_oid: If set AND a real commit is produced, verify the
            new commit's first parent matches the captured oid.  Skipped when
            ``allow_empty`` is True and the commit was a no-op (nothing was
            actually committed).  Mismatch returns ``False`` after the commit
            was already made — the caller should treat this as "another
            process committed concurrently" and decide whether to revert /
            retry.

    Returns:
        True if commit succeeded (or nothing to commit with allow_empty=True),
        False otherwise

    Example:
        >>> from pathlib import Path
        >>> safe_commit(
        ...     repo_path=Path("."),
        ...     files_to_commit=[Path("kitty-specs/038-feature/tasks/WP01.md")],
        ...     commit_message="Update WP01 status to doing",
        ...     allow_empty=False
        ... )
        True
    """
    # Defence-in-depth: verify the branch BEFORE we touch the index, so a
    # concurrent ``git checkout`` between resolve and commit fails fast
    # instead of landing the commit on the wrong branch.
    if expected_branch is not None:
        actual_branch = _current_branch(repo_path)
        if actual_branch != expected_branch:
            logger.warning(
                "Refusing safe_commit in %s: expected branch %r but HEAD is on %r",
                repo_path,
                expected_branch,
                actual_branch,
            )
            return False

    # Normalize file paths to be relative to repo_path
    normalized_files = []
    for file in files_to_commit:
        if file.is_absolute():
            try:
                file = file.relative_to(repo_path)
            except ValueError:
                # File is not under repo_path, use as-is
                pass
        normalized_files.append(str(file))

    # Save current staging area (only staged changes, not working tree)
    stash_result = subprocess.run(
        ["git", "stash", "push", "--staged", "--quiet"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    # Track if we stashed anything (needed for cleanup)
    stashed_something = stash_result.returncode == 0

    try:
        # Stage only the intended files
        for file_path in normalized_files:
            add_result = subprocess.run(
                # Use --force for explicitly-requested files so ignored
                # status files can still be committed intentionally.
                ["git", "add", "--force", "--", file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if add_result.returncode != 0:
                # Failed to stage file
                return False

        # Commit the staged files
        commit_cmd = ["git", "commit"]
        if no_verify:
            commit_cmd.append("--no-verify")
        commit_cmd.extend(["-m", commit_message])
        commit_result = subprocess.run(
            commit_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        # Check for success
        if commit_result.returncode == 0:
            # Defence-in-depth: verify the new commit's parent matches the
            # oid the caller captured immediately after ensuring the branch.
            # Mismatch means another process slipped a commit in between
            # resolve+ensure and the commit we just produced — the commit
            # is still made (we cannot atomically un-commit), but the
            # caller should treat False as "concurrent modification, please
            # reconcile".
            if expected_parent_oid is not None:
                parent_result = subprocess.run(
                    ["git", "rev-parse", "HEAD^"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if parent_result.returncode == 0:
                    actual_parent = parent_result.stdout.strip()
                    if actual_parent != expected_parent_oid:
                        logger.warning(
                            "safe_commit in %s landed a commit whose parent "
                            "%s does not match the expected parent %s; "
                            "another process likely committed concurrently",
                            repo_path,
                            actual_parent,
                            expected_parent_oid,
                        )
                        return False
            return True

        # Check if it was "nothing to commit" scenario
        if "nothing to commit" in commit_result.stdout or "nothing to commit" in commit_result.stderr:
            return allow_empty

        # Other error occurred
        return False

    finally:
        # Restore original staging area if we stashed anything
        if stashed_something:
            subprocess.run(
                ["git", "stash", "pop", "--index", "--quiet"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
