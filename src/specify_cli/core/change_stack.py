"""Change stack management - stash routing, request validation, and policy enforcement.

Implements branch-aware stash routing (FR-003), ambiguity fail-fast validation
(FR-002A), and closed/done link-only policy (FR-016) for the /spec-kitty.change
command.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from specify_cli.core.change_classifier import ComplexityScore, classify_change_request
from specify_cli.core.git_ops import get_current_branch
from specify_cli.core.feature_detection import _get_main_repo_root
from specify_cli.tasks_support import LANES


# ============================================================================
# Types
# ============================================================================


class StashScope(str, Enum):
    """Scope type for branch stash routing."""
    MAIN = "main"
    FEATURE = "feature"


class ValidationState(str, Enum):
    """Validation state for change requests."""
    VALID = "valid"
    AMBIGUOUS = "ambiguous"
    BLOCKED = "blocked"


# Embedded main stash path (not a pseudo-feature directory).
# Per plan.md: "On main or master: route to embedded main stash path
# kitty-specs/change-stack/main/"
MAIN_STASH_RELATIVE = Path("kitty-specs") / "change-stack" / "main"

# Primary branch names that route to the main stash.
PRIMARY_BRANCHES = frozenset({"main", "master"})

# Patterns indicating ambiguous change requests (FR-002A).
# These are requests that reference targets without specifying them.
_AMBIGUOUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bthis\s+block\b", re.IGNORECASE),
    re.compile(r"\bthat\s+block\b", re.IGNORECASE),
    re.compile(r"\bthis\s+section\b", re.IGNORECASE),
    re.compile(r"\bthat\s+section\b", re.IGNORECASE),
    re.compile(r"\bthis\s+part\b", re.IGNORECASE),
    re.compile(r"\bthat\s+part\b", re.IGNORECASE),
    re.compile(r"\bhere\b", re.IGNORECASE),
    re.compile(r"\bthere\b", re.IGNORECASE),
]

# Patterns that disambiguate - if present alongside an ambiguous pattern,
# the request is considered clear enough to proceed.
_DISAMBIGUATING_PATTERNS: list[re.Pattern[str]] = [
    # Explicit file/path references
    re.compile(r"[a-zA-Z_/]+\.(py|ts|js|md|yaml|yml|json|toml|rs|go|java|rb)\b"),
    # Explicit function/class references
    re.compile(r"\b(function|class|method|module|file|directory)\s+\w+", re.IGNORECASE),
    # Explicit WP references
    re.compile(r"\bWP\d{2}\b"),
    # Quoted identifiers
    re.compile(r'["`\'][\w.]+["`\']'),
]

# Closed/done lanes that must not be reopened (FR-016).
CLOSED_LANES = frozenset({"done"})


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class BranchStash:
    """Scope-aware destination for generated change work.

    Attributes:
        stash_key: 'main' or feature slug (e.g., '029-mid-stream-change-command')
        scope: Whether this targets main or a feature branch
        stash_path: Absolute path to the stash directory
        tasks_doc_path: Absolute path to tasks.md (if applicable)
    """
    stash_key: str
    scope: StashScope
    stash_path: Path
    tasks_doc_path: Optional[Path] = None


@dataclass
class AmbiguityResult:
    """Result of ambiguity analysis for a change request.

    Attributes:
        is_ambiguous: True if the request lacks sufficient target specificity
        matched_patterns: List of ambiguous pattern descriptions that triggered
        clarification_prompt: Suggested prompt to resolve ambiguity
    """
    is_ambiguous: bool
    matched_patterns: list[str] = field(default_factory=list)
    clarification_prompt: Optional[str] = None


@dataclass
class ClosedReferenceCheck:
    """Result of checking references to closed/done work packages.

    Attributes:
        has_closed_references: True if request references closed/done WPs
        closed_wp_ids: List of referenced closed/done WP IDs
        linkable: True if the references can be used as link-only context
    """
    has_closed_references: bool
    closed_wp_ids: list[str] = field(default_factory=list)
    linkable: bool = True


@dataclass
class ChangeRequest:
    """Parsed and validated change request.

    Attributes:
        request_id: Unique identifier for this request
        raw_text: Original request text
        submitted_branch: Branch the request was submitted from
        stash: Resolved branch stash
        validation_state: Current validation state
        ambiguity: Ambiguity analysis result
        closed_references: Closed WP reference check result
        complexity_score: Deterministic complexity scoring result (FR-009)
    """
    request_id: str
    raw_text: str
    submitted_branch: str
    stash: BranchStash
    validation_state: ValidationState
    ambiguity: AmbiguityResult
    closed_references: ClosedReferenceCheck
    complexity_score: Optional[ComplexityScore] = None


# ============================================================================
# Stash Resolution (T007)
# ============================================================================


def resolve_stash(repo_root: Path, branch: Optional[str] = None) -> BranchStash:
    """Resolve the branch stash from the active branch context.

    Routes to the correct stash based on the current branch:
    - main/master -> kitty-specs/change-stack/main/
    - feature branch (###-name) -> kitty-specs/<feature>/tasks/
    - worktree branch (###-name-WP##) -> kitty-specs/<feature>/tasks/

    Args:
        repo_root: Repository root path (may be worktree)
        branch: Override branch name (auto-detected if None)

    Returns:
        BranchStash with resolved scope and paths

    Raises:
        ChangeStackError: If branch context cannot be resolved
    """
    main_repo = _get_main_repo_root(repo_root)

    if branch is None:
        branch = get_current_branch(repo_root)
        if branch is None:
            raise ChangeStackError(
                "Could not determine current branch. "
                "Ensure you are in a git repository with a checked-out branch."
            )

    # Check for primary branches (main/master)
    if branch in PRIMARY_BRANCHES:
        stash_path = main_repo / MAIN_STASH_RELATIVE
        tasks_doc = stash_path / "tasks.md"
        return BranchStash(
            stash_key="main",
            scope=StashScope.MAIN,
            stash_path=stash_path,
            tasks_doc_path=tasks_doc if tasks_doc.exists() else None,
        )

    # Check for feature branch pattern (###-feature-name or ###-feature-name-WP##)
    # Strip -WP## suffix if present (worktree branch)
    feature_slug = _extract_feature_slug(branch)
    if feature_slug is not None:
        feature_dir = main_repo / "kitty-specs" / feature_slug
        stash_path = feature_dir / "tasks"
        tasks_doc = feature_dir / "tasks.md"
        return BranchStash(
            stash_key=feature_slug,
            scope=StashScope.FEATURE,
            stash_path=stash_path,
            tasks_doc_path=tasks_doc if tasks_doc.exists() else None,
        )

    # Detached HEAD or unrecognized branch pattern
    raise ChangeStackError(
        f"Cannot resolve stash for branch '{branch}'. "
        f"Expected 'main', 'master', or a feature branch (###-feature-name). "
        f"If you are in detached HEAD state, checkout a branch first."
    )


def _extract_feature_slug(branch: str) -> Optional[str]:
    """Extract feature slug from a branch name.

    Handles both direct feature branches and worktree WP branches:
    - '029-mid-stream-change' -> '029-mid-stream-change'
    - '029-mid-stream-change-WP01' -> '029-mid-stream-change'

    Args:
        branch: Git branch name

    Returns:
        Feature slug or None if branch doesn't match feature pattern
    """
    # Try worktree WP branch first (more specific pattern)
    wp_match = re.match(r'^((\d{3})-.+)-WP\d{2}$', branch)
    if wp_match:
        return wp_match.group(1)

    # Try direct feature branch
    feature_match = re.match(r'^(\d{3}-.+)$', branch)
    if feature_match:
        return feature_match.group(1)

    return None


# ============================================================================
# Ambiguity Detection (T010)
# ============================================================================


def check_ambiguity(request_text: str) -> AmbiguityResult:
    """Check if a change request is ambiguous about its target.

    A request is ambiguous if it contains vague references ("this block",
    "that section") without any disambiguating context (file names, function
    names, WP IDs, or quoted identifiers).

    Per FR-002A: The system MUST fail fast and request clarification before
    creating any change work package when the target scope is ambiguous.

    Args:
        request_text: The natural-language change request

    Returns:
        AmbiguityResult indicating whether clarification is needed
    """
    if not request_text or not request_text.strip():
        return AmbiguityResult(
            is_ambiguous=True,
            matched_patterns=["empty request"],
            clarification_prompt="Please provide a change request description.",
        )

    # Check for disambiguating patterns first - if present, request is clear
    for pattern in _DISAMBIGUATING_PATTERNS:
        if pattern.search(request_text):
            return AmbiguityResult(is_ambiguous=False)

    # Check for ambiguous patterns
    matched: list[str] = []
    for pattern in _AMBIGUOUS_PATTERNS:
        match = pattern.search(request_text)
        if match:
            matched.append(match.group())

    if matched:
        prompt_parts = [
            "Your change request contains vague references that could apply "
            "to multiple locations:",
            "",
        ]
        for m in matched:
            prompt_parts.append(f"  - '{m}'")
        prompt_parts.extend([
            "",
            "Please clarify by specifying:",
            "  - File path(s) affected",
            "  - Function or class name(s)",
            "  - Work package ID(s) (e.g., WP01)",
        ])

        return AmbiguityResult(
            is_ambiguous=True,
            matched_patterns=matched,
            clarification_prompt="\n".join(prompt_parts),
        )

    return AmbiguityResult(is_ambiguous=False)


# ============================================================================
# Closed/Done Policy Enforcement (T011)
# ============================================================================


def check_closed_references(
    request_text: str,
    repo_root: Path,
    feature_slug: str,
) -> ClosedReferenceCheck:
    """Check if a change request references closed/done work packages.

    Per FR-016: When a request references a closed/done WP, create a new
    change WP linked to it as historical context. Never reopen.

    Args:
        request_text: The change request text
        repo_root: Repository root path
        feature_slug: Feature slug for WP lookup

    Returns:
        ClosedReferenceCheck with identified closed WP references
    """
    # Find WP references in request text
    wp_pattern = re.compile(r'\bWP(\d{2})\b')
    wp_matches = wp_pattern.findall(request_text)

    if not wp_matches:
        return ClosedReferenceCheck(has_closed_references=False)

    main_repo = _get_main_repo_root(repo_root)
    tasks_dir = main_repo / "kitty-specs" / feature_slug / "tasks"

    closed_ids: list[str] = []

    for wp_num in wp_matches:
        wp_id = f"WP{wp_num}"
        lane = _get_wp_lane(tasks_dir, wp_id)
        if lane in CLOSED_LANES:
            closed_ids.append(wp_id)

    return ClosedReferenceCheck(
        has_closed_references=bool(closed_ids),
        closed_wp_ids=closed_ids,
        linkable=True,  # Always linkable, never reopenable
    )


def _get_wp_lane(tasks_dir: Path, wp_id: str) -> Optional[str]:
    """Get the lane status of a work package from its frontmatter.

    Args:
        tasks_dir: Path to the tasks directory
        wp_id: Work package ID (e.g., "WP01")

    Returns:
        Lane string or None if WP not found
    """
    if not tasks_dir.exists():
        return None

    wp_files = list(tasks_dir.glob(f"{wp_id}-*.md"))
    if not wp_files:
        return None

    # Read frontmatter to get lane
    content = wp_files[0].read_text(encoding="utf-8")
    lane_match = re.search(r'^lane:\s*["\']?(\w+)["\']?\s*$', content, re.MULTILINE)
    if lane_match:
        return lane_match.group(1)

    return None


def validate_no_closed_mutation(
    wp_ids: list[str],
    tasks_dir: Path,
) -> list[str]:
    """Validate that no closed/done WPs would be mutated.

    Per FR-016: The system MUST NOT reopen closed/done WPs.

    Args:
        wp_ids: WP IDs to check
        tasks_dir: Path to the tasks directory

    Returns:
        List of WP IDs that are closed/done and must not be mutated.
        Empty list means all WPs are safe to modify.
    """
    blocked: list[str] = []
    for wp_id in wp_ids:
        lane = _get_wp_lane(tasks_dir, wp_id)
        if lane in CLOSED_LANES:
            blocked.append(wp_id)
    return blocked


# ============================================================================
# Request Validation (T009, T010)
# ============================================================================


def validate_change_request(
    request_text: str,
    repo_root: Path,
    branch: Optional[str] = None,
    feature: Optional[str] = None,
) -> ChangeRequest:
    """Validate and prepare a change request for processing.

    Performs all pre-write validation:
    1. Resolves branch stash (FR-003)
    2. Checks for ambiguity (FR-002A)
    3. Checks for closed WP references (FR-016)

    Args:
        request_text: Natural-language change request
        repo_root: Repository root path
        branch: Override branch name (auto-detected if None)
        feature: Override feature slug (auto-detected from stash if None)

    Returns:
        ChangeRequest with validation results

    Raises:
        ChangeStackError: If stash cannot be resolved
    """
    # Step 1: Resolve stash
    stash = resolve_stash(repo_root, branch=branch)

    # Step 2: Check ambiguity
    ambiguity = check_ambiguity(request_text)

    # Step 3: Check closed references
    feature_slug = feature or stash.stash_key
    closed_refs = check_closed_references(request_text, repo_root, feature_slug)

    # Step 4: Classify complexity (FR-009) - runs even for ambiguous requests
    # so preview can show the score breakdown
    complexity = classify_change_request(request_text)

    # Determine overall validation state
    if ambiguity.is_ambiguous:
        state = ValidationState.AMBIGUOUS
    else:
        state = ValidationState.VALID

    request_id = str(uuid.uuid4())[:8]

    return ChangeRequest(
        request_id=request_id,
        raw_text=request_text,
        submitted_branch=branch or get_current_branch(repo_root) or "unknown",
        stash=stash,
        validation_state=state,
        ambiguity=ambiguity,
        closed_references=closed_refs,
        complexity_score=complexity,
    )


# ============================================================================
# Errors
# ============================================================================


class ChangeStackError(Exception):
    """Error during change stack operations."""
    pass
