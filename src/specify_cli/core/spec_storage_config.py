"""Spec storage configuration for orphan-branch-based spec management.

This module provides the configuration schema, read/write accessors,
and validation for the ``spec_storage`` block in ``.kittify/config.yaml``.

The spec_storage config controls where planning artifacts (specs, plans,
work packages) are stored - on an orphan branch managed via a git worktree.

Key design decisions:
- Config lives in ``.kittify/config.yaml`` (stays on development branch).
- ``auto_push`` defaults to ``False``.
- Missing ``spec_storage`` keys indicate a legacy layout (not auto-migrated).
- Validation is reusable by init, check, and migration commands.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BRANCH_NAME = "kitty-specs"
DEFAULT_WORKTREE_PATH = "kitty-specs"
DEFAULT_AUTO_PUSH = False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SpecStorageConfigError(RuntimeError):
    """Raised when spec_storage configuration is invalid or cannot be parsed."""


# ---------------------------------------------------------------------------
# Data model  (T001)
# ---------------------------------------------------------------------------


@dataclass
class SpecStorageConfig:
    """Repository-level spec storage settings.

    Attributes:
        branch_name: Name of the orphan branch for planning artifacts.
        worktree_path: Relative path (from repo root) for the worktree checkout.
        auto_push: Whether to push automatically after local commits.
        is_defaulted: True when the config was synthesised from defaults
            (i.e. the ``spec_storage`` key was absent from the YAML file).
    """

    branch_name: str = DEFAULT_BRANCH_NAME
    worktree_path: str = DEFAULT_WORKTREE_PATH
    auto_push: bool = DEFAULT_AUTO_PUSH
    is_defaulted: bool = False


# ---------------------------------------------------------------------------
# Read / write accessors  (T002)
# ---------------------------------------------------------------------------


def _config_file_path(repo_root: Path) -> Path:
    """Return the canonical path to ``.kittify/config.yaml``."""
    return repo_root / ".kittify" / "config.yaml"


def has_spec_storage_config(repo_root: Path) -> bool:
    """Check whether ``spec_storage`` section exists in the config file.

    Returns ``False`` for legacy repos that do not yet have the key.
    """
    config_file = _config_file_path(repo_root)
    if not config_file.exists():
        return False

    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(config_file, "r", encoding="utf-8") as fh:
            data = yaml.load(fh) or {}
    except Exception:
        return False

    return "spec_storage" in data


def load_spec_storage_config(repo_root: Path) -> SpecStorageConfig:
    """Load ``spec_storage`` settings from ``.kittify/config.yaml``.

    Missing keys are filled with defaults.  If the entire
    ``spec_storage`` block is absent the returned object has
    ``is_defaulted=True``.

    Raises:
        SpecStorageConfigError: If the YAML file cannot be parsed.
    """
    config_file = _config_file_path(repo_root)

    if not config_file.exists():
        logger.info("Config file not found at %s, returning defaults", config_file)
        return SpecStorageConfig(is_defaulted=True)

    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(config_file, "r", encoding="utf-8") as fh:
            data = yaml.load(fh) or {}
    except Exception as exc:
        raise SpecStorageConfigError(
            f"Invalid YAML in {config_file}: {exc}"
        ) from exc

    spec_data = data.get("spec_storage")
    if spec_data is None:
        logger.info("No spec_storage section in %s, returning defaults", config_file)
        return SpecStorageConfig(is_defaulted=True)

    if not isinstance(spec_data, dict):
        raise SpecStorageConfigError(
            f"spec_storage in {config_file} must be a mapping, "
            f"got {type(spec_data).__name__}"
        )

    return SpecStorageConfig(
        branch_name=spec_data.get("branch_name", DEFAULT_BRANCH_NAME),
        worktree_path=spec_data.get("worktree_path", DEFAULT_WORKTREE_PATH),
        auto_push=spec_data.get("auto_push", DEFAULT_AUTO_PUSH),
        is_defaulted=False,
    )


def save_spec_storage_config(
    repo_root: Path,
    config: SpecStorageConfig,
) -> None:
    """Save ``spec_storage`` settings to ``.kittify/config.yaml``.

    Merges with existing config (preserves other sections like ``vcs``
    and ``agents``).  Creates the file and directory if they do not exist.
    """
    config_dir = repo_root / ".kittify"
    config_file = config_dir / "config.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as fh:
            data = yaml.load(fh) or {}
    else:
        data = {}
        config_dir.mkdir(parents=True, exist_ok=True)

    data["spec_storage"] = {
        "branch_name": config.branch_name,
        "worktree_path": config.worktree_path,
        "auto_push": config.auto_push,
    }

    with open(config_file, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)

    logger.info("Saved spec_storage config to %s", config_file)


def get_spec_worktree_abs_path(
    repo_root: Path,
    config: SpecStorageConfig | None = None,
) -> Path:
    """Derive the absolute worktree path from ``repo_root`` + config value.

    Normalises separators and avoids trailing-slash ambiguity.
    """
    if config is None:
        config = load_spec_storage_config(repo_root)

    # Normalise the configured path (handles backslashes on Windows)
    relative = Path(config.worktree_path)
    absolute = (repo_root / relative).resolve()
    return absolute


# ---------------------------------------------------------------------------
# Validation  (T003)
# ---------------------------------------------------------------------------

# Git branch name rules (simplified from git-check-ref-format):
#  - Cannot contain: space, ~, ^, :, \, control chars, DEL, ..
#  - Cannot start with - or .
#  - Cannot end with .lock
#  - Cannot contain consecutive dots (..)
#  - Cannot be empty
#  - Cannot contain backslash
#  - Cannot contain ASCII control chars (0x00-0x1f, 0x7f)
#  - Cannot contain [ (used in reflog syntax)
_INVALID_BRANCH_CHARS_RE = re.compile(
    r"[\x00-\x1f\x7f ~^:\\?*\[" r"]"
)


def _is_valid_git_branch_name(name: str) -> tuple[bool, str]:
    """Validate a string as a legal git branch name.

    Returns ``(True, "")`` on success or ``(False, reason)`` on failure.
    Uses a subset of rules from ``git check-ref-format --branch``.
    """
    if not name:
        return False, "branch name must not be empty"

    if name.startswith("-"):
        return False, "branch name must not start with '-'"

    if name.startswith("."):
        return False, "branch name must not start with '.'"

    if name.endswith(".lock"):
        return False, "branch name must not end with '.lock'"

    if name.endswith("."):
        return False, "branch name must not end with '.'"

    if ".." in name:
        return False, "branch name must not contain '..'"

    if name.endswith("/"):
        return False, "branch name must not end with '/'"

    if " " in name:
        return False, "branch name must not contain spaces"

    match = _INVALID_BRANCH_CHARS_RE.search(name)
    if match:
        char = match.group()
        return False, f"branch name contains invalid character: {char!r}"

    if "@{" in name:
        return False, "branch name must not contain '@{{'"

    return True, ""


def validate_spec_storage_config(
    config: SpecStorageConfig,
    repo_root: Path,
) -> list[str]:
    """Validate ``spec_storage`` config values.

    Returns a list of human-readable error strings.  An empty list
    means the config is valid.  Each error mentions the exact failing
    key and the expected shape.
    """
    errors: list[str] = []

    # --- branch_name ---
    if not isinstance(config.branch_name, str):
        errors.append(
            f"spec_storage.branch_name: expected string, "
            f"got {type(config.branch_name).__name__}"
        )
    else:
        ok, reason = _is_valid_git_branch_name(config.branch_name)
        if not ok:
            errors.append(
                f"spec_storage.branch_name: {config.branch_name!r} is not a "
                f"valid git branch name ({reason})"
            )

    # --- worktree_path ---
    if not isinstance(config.worktree_path, str):
        errors.append(
            f"spec_storage.worktree_path: expected string, "
            f"got {type(config.worktree_path).__name__}"
        )
    elif not config.worktree_path:
        errors.append("spec_storage.worktree_path: must not be empty")
    else:
        try:
            resolved = (repo_root / config.worktree_path).resolve()
            repo_resolved = repo_root.resolve()
            # The worktree path must be inside or at the repo root
            try:
                resolved.relative_to(repo_resolved)
            except ValueError:
                errors.append(
                    f"spec_storage.worktree_path: {config.worktree_path!r} "
                    f"resolves outside repository root"
                )
        except (OSError, ValueError) as exc:
            errors.append(
                f"spec_storage.worktree_path: cannot resolve "
                f"{config.worktree_path!r}: {exc}"
            )

    # --- auto_push ---
    if not isinstance(config.auto_push, bool):
        errors.append(
            f"spec_storage.auto_push: expected boolean, "
            f"got {type(config.auto_push).__name__} {config.auto_push!r}"
        )

    return errors


def validate_spec_storage_raw(
    raw_data: dict[str, Any],
    repo_root: Path,
) -> list[str]:
    """Validate raw YAML data before constructing a ``SpecStorageConfig``.

    This catches type mismatches that would otherwise be silently coerced
    by the dataclass constructor (e.g. ``auto_push: "yes"``).
    """
    errors: list[str] = []

    if not isinstance(raw_data, dict):
        return [
            f"spec_storage: expected a mapping, got {type(raw_data).__name__}"
        ]

    # Check auto_push is actually boolean (YAML may parse "yes"/"no" as bool,
    # but explicit string values like "yes" in quotes should fail).
    auto_push = raw_data.get("auto_push", DEFAULT_AUTO_PUSH)
    if not isinstance(auto_push, bool):
        errors.append(
            f"spec_storage.auto_push: expected boolean, "
            f"got {type(auto_push).__name__} {auto_push!r}"
        )

    branch_name = raw_data.get("branch_name", DEFAULT_BRANCH_NAME)
    if not isinstance(branch_name, str):
        errors.append(
            f"spec_storage.branch_name: expected string, "
            f"got {type(branch_name).__name__}"
        )
    else:
        ok, reason = _is_valid_git_branch_name(branch_name)
        if not ok:
            errors.append(
                f"spec_storage.branch_name: {branch_name!r} is not a "
                f"valid git branch name ({reason})"
            )

    worktree_path = raw_data.get("worktree_path", DEFAULT_WORKTREE_PATH)
    if not isinstance(worktree_path, str):
        errors.append(
            f"spec_storage.worktree_path: expected string, "
            f"got {type(worktree_path).__name__}"
        )
    elif not worktree_path:
        errors.append("spec_storage.worktree_path: must not be empty")
    else:
        try:
            resolved = (repo_root / worktree_path).resolve()
            repo_resolved = repo_root.resolve()
            try:
                resolved.relative_to(repo_resolved)
            except ValueError:
                errors.append(
                    f"spec_storage.worktree_path: {worktree_path!r} "
                    f"resolves outside repository root"
                )
        except (OSError, ValueError) as exc:
            errors.append(
                f"spec_storage.worktree_path: cannot resolve "
                f"{worktree_path!r}: {exc}"
            )

    return errors


__all__ = [
    "DEFAULT_AUTO_PUSH",
    "DEFAULT_BRANCH_NAME",
    "DEFAULT_WORKTREE_PATH",
    "SpecStorageConfig",
    "SpecStorageConfigError",
    "get_spec_worktree_abs_path",
    "has_spec_storage_config",
    "load_spec_storage_config",
    "save_spec_storage_config",
    "validate_spec_storage_config",
    "validate_spec_storage_raw",
]
