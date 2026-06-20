"""Advisory filesystem lock around kitty-specs commit operations.

Multiple `spec-kitty` invocations — or one CLI call racing a manual
`git commit` in the kitty-specs worktree — can interleave their resolve →
checkout → write → stage → commit sequences and produce surprising
"reverted" lane states.  This module provides a per-worktree advisory lock
that serialises those critical sections.

The lock is **advisory** (cooperative), worktree-scoped, and
self-cleaning:

* lock file lives inside the per-worktree git directory
  (resolved via ``git rev-parse --git-dir``) so it is always under a real
  directory even for ``git worktree add``-style checkouts, and so the file
  never gets committed accidentally
* takes ``fcntl.flock(LOCK_EX | LOCK_NB)`` on POSIX, with a polling retry
  loop up to the configured timeout
* on Windows / when ``fcntl`` is unavailable, falls back to an O_EXCL
  sentinel file that records the holder's PID so a stale lock from a
  crashed process can be cleared
* the lock file remains on disk after release (kept open and reused by
  later invocations) so concurrent lock attempts can ``flock`` it without
  racing on create/unlink

Use as a context manager::

    with kitty_specs_lock(commit_repo_root):
        commit_context = resolve_specs_repo_and_branch(...)
        ensure_branch_checked_out(commit_context)
        wp.path.write_text(updated_doc)
        safe_commit(...)

Timeout precedence:

1. ``timeout_s`` argument
2. ``SPEC_KITTY_LOCK_TIMEOUT_S`` environment variable (parsed as float)
3. ``DEFAULT_LOCK_TIMEOUT_S`` module constant (30.0 seconds)
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


DEFAULT_LOCK_TIMEOUT_S: float = 30.0
"""Default seconds to wait when acquiring the lock before failing."""

LOCK_FILE_BASENAME: str = "spec-kitty.lock"
"""Lock file name placed inside the per-worktree git directory."""

_POLL_INTERVAL_S: float = 0.05
"""Polling interval between non-blocking flock attempts."""

_ENV_TIMEOUT_VAR: str = "SPEC_KITTY_LOCK_TIMEOUT_S"


try:
    import fcntl  # type: ignore[attr-defined]

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows fallback path
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False


class LockTimeoutError(RuntimeError):
    """Raised when the spec-kitty lock cannot be acquired within the timeout."""


def _resolve_git_dir(repo_root: Path) -> Path:
    """Return the per-worktree git directory for ``repo_root``.

    For a normal repository this is ``<repo_root>/.git``; for a ``git
    worktree add`` checkout this is the worktree-specific state directory
    under the main repo's ``.git/worktrees/<name>/``.  We resolve it via
    ``git rev-parse --git-dir`` rather than assuming a layout because a
    worktree's ``.git`` is a file, not a directory.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        git_dir = Path(result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = (repo_root / git_dir).resolve()
        return git_dir

    # Fall back to a .kittify-anchored locks dir when the path isn't a git
    # repo (e.g. integration tests using a non-git directory).  This keeps
    # the lock co-located with the project even without git.
    fallback = repo_root / ".kittify" / "locks"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _resolve_timeout(explicit: float | None) -> float:
    if explicit is not None:
        return max(0.0, float(explicit))
    raw = os.environ.get(_ENV_TIMEOUT_VAR, "").strip()
    if not raw:
        return DEFAULT_LOCK_TIMEOUT_S
    try:
        parsed = float(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r; falling back to %.1fs",
            _ENV_TIMEOUT_VAR,
            raw,
            DEFAULT_LOCK_TIMEOUT_S,
        )
        return DEFAULT_LOCK_TIMEOUT_S
    return max(0.0, parsed)


def _acquire_flock(lock_path: Path, timeout_s: float):
    """Acquire an exclusive ``fcntl`` lock on ``lock_path``.

    Returns the open file handle (caller must keep it open and close it on
    release).  Raises :class:`LockTimeoutError` on timeout.
    """
    assert _HAS_FCNTL and fcntl is not None  # nosec
    handle = open(lock_path, "a+")  # noqa: SIM115 - kept open intentionally
    deadline = time.monotonic() + timeout_s
    first_attempt = True
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate(0)
            handle.write(str(os.getpid()))
            handle.flush()
            return handle
        except BlockingIOError:
            if first_attempt:
                logger.info(
                    "Waiting for kitty-specs lock at %s "
                    "(another spec-kitty process is active)",
                    lock_path,
                )
                first_attempt = False
            if time.monotonic() >= deadline:
                handle.close()
                raise LockTimeoutError(
                    f"Timed out after {timeout_s:.1f}s waiting for the "
                    f"kitty-specs lock at {lock_path}.  Another spec-kitty "
                    "process may be stuck; check for lingering invocations "
                    f"or remove the lock file manually if appropriate."
                )
            time.sleep(_POLL_INTERVAL_S)


def _read_pid(lock_path: Path) -> int | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user.  Treat as alive.
        return True
    except OSError:
        return False
    return True


def _acquire_sentinel(lock_path: Path, timeout_s: float):
    """Pure-Python fallback when ``fcntl`` is unavailable (Windows).

    Uses ``O_CREAT | O_EXCL`` to atomically claim the lock file, retrying
    until the timeout elapses.  Detects and clears stale locks whose
    recorded PID is no longer alive.
    """
    deadline = time.monotonic() + timeout_s
    first_attempt = True
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            return lock_path
        except FileExistsError:
            existing_pid = _read_pid(lock_path)
            if existing_pid is not None and not _pid_alive(existing_pid):
                # Stale lock from a crashed process.  Try to clear it.
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                # Loop to retry the O_EXCL claim.
                continue
            if first_attempt:
                logger.info(
                    "Waiting for kitty-specs lock at %s "
                    "(another spec-kitty process is active)",
                    lock_path,
                )
                first_attempt = False
            if time.monotonic() >= deadline:
                raise LockTimeoutError(
                    f"Timed out after {timeout_s:.1f}s waiting for the "
                    f"kitty-specs lock at {lock_path}.  Holder PID "
                    f"recorded as {existing_pid}; clear the file manually "
                    "if that process is gone."
                )
            time.sleep(_POLL_INTERVAL_S)


@contextlib.contextmanager
def kitty_specs_lock(
    repo_root: Path,
    *,
    timeout_s: float | None = None,
) -> Iterator[None]:
    """Acquire an advisory lock on ``repo_root`` for kitty-specs writes.

    ``repo_root`` should be the resolved commit repo root — i.e. the
    kitty-specs worktree root when one exists, otherwise the main repo
    root.  Callers that have not yet resolved the commit context can pass
    the prospective worktree path (``main_repo_root / "kitty-specs"``) or
    the main repo root; the lock is per-worktree-git-dir, so two callers
    acquiring on different paths that resolve to the same worktree will
    serialise correctly.

    Yields control once the lock is held.  Releases on exit or exception.
    """
    git_dir = _resolve_git_dir(repo_root)
    try:
        git_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Could not create lock directory {git_dir}: {exc}"
        ) from exc

    lock_path = git_dir / LOCK_FILE_BASENAME
    timeout = _resolve_timeout(timeout_s)

    if _HAS_FCNTL:
        handle = _acquire_flock(lock_path, timeout)
        try:
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
            except OSError:
                pass
            handle.close()
        return

    # Windows / no-fcntl fallback.
    claimed = _acquire_sentinel(lock_path, timeout)
    try:
        yield
    finally:
        try:
            claimed.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_S",
    "LOCK_FILE_BASENAME",
    "LockTimeoutError",
    "kitty_specs_lock",
]
