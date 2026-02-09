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

import textwrap
from datetime import datetime, timezone

from specify_cli.core.change_classifier import (
    ComplexityScore,
    PackagingMode,
    ReviewAttention,
    classify_change_request,
)
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
# Change Plan and WP Synthesis (T018-T022)
# ============================================================================


@dataclass
class ChangePlan:
    """Planner decision layer for decomposition and guardrails.

    Attributes:
        request_id: Trace ID linking to the ChangeRequest
        mode: Packaging mode selected deterministically
        affected_open_wp_ids: Open WPs referenced in the request
        closed_reference_wp_ids: Closed WPs for link-only context
        guardrails: User-specified constraints to include in generated WPs
        requires_merge_coordination: Whether merge coordination jobs are needed
    """
    request_id: str
    mode: PackagingMode
    affected_open_wp_ids: list[str] = field(default_factory=list)
    closed_reference_wp_ids: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    requires_merge_coordination: bool = False


@dataclass
class ChangeWorkPackage:
    """Generated change WP entry ready to write to the tasks directory.

    Attributes:
        work_package_id: e.g., "WP09"
        title: Derived from request text
        filename: Slugged filename, e.g., "WP09-use-sqlalchemy.md"
        lane: Always "planned" for generated WPs
        dependencies: WP IDs this WP depends on
        change_stack: Always True for change WPs
        change_request_id: Trace ID to originating request
        change_mode: Packaging mode label
        stack_rank: Ordering rank within the change set
        review_attention: Normal or elevated
        closed_reference_links: Link-only references to closed WPs
        body: Full markdown body including frontmatter
    """
    work_package_id: str
    title: str
    filename: str
    lane: str = "planned"
    dependencies: list[str] = field(default_factory=list)
    change_stack: bool = True
    change_request_id: str = ""
    change_mode: str = ""
    stack_rank: int = 1
    review_attention: str = "normal"
    closed_reference_links: list[str] = field(default_factory=list)
    body: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-friendly dictionary."""
        return {
            "workPackageId": self.work_package_id,
            "title": self.title,
            "filename": self.filename,
            "lane": self.lane,
            "dependencies": self.dependencies,
            "changeStack": self.change_stack,
            "changeRequestId": self.change_request_id,
            "changeMode": self.change_mode,
            "stackRank": self.stack_rank,
            "reviewAttention": self.review_attention,
            "closedReferenceLinks": self.closed_reference_links,
        }


def _next_wp_id(tasks_dir: Path) -> str:
    """Allocate the next available WP ID deterministically (T019).

    Scans existing WP files in the tasks directory (and virtual registry
    for in-flight batch generation) and returns the next sequential ID.
    IDs are zero-padded to two digits: WP01, WP02, ..., WP99.

    Args:
        tasks_dir: Path to the flat tasks directory

    Returns:
        Next WP ID string, e.g., "WP09"
    """
    existing_ids: set[int] = set()
    if tasks_dir.exists():
        for f in tasks_dir.glob("WP[0-9][0-9]-*.md"):
            try:
                num = int(f.name[2:4])
                existing_ids.add(num)
            except ValueError:
                continue

    # Also check virtual registry for in-flight allocations
    key = str(tasks_dir)
    if key in _virtual_wp_registry:
        for fname in _virtual_wp_registry[key]:
            try:
                num = int(fname[2:4])
                existing_ids.add(num)
            except (ValueError, IndexError):
                continue

    next_num = 1
    while next_num in existing_ids:
        next_num += 1

    return f"WP{next_num:02d}"


def _slugify(text: str, max_length: int = 40) -> str:
    """Create a URL-safe slug from text for filenames.

    Args:
        text: Raw text to slugify
        max_length: Maximum slug length

    Returns:
        Lowercased, hyphenated slug
    """
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', text.lower())
    slug = re.sub(r'[\s_]+', '-', slug.strip())
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('-', 1)[0]
    return slug or "change"


def _derive_title(request_text: str, max_length: int = 60) -> str:
    """Derive a concise WP title from the request text.

    Args:
        request_text: Original change request
        max_length: Maximum title length

    Returns:
        A clean title string
    """
    # Take first sentence or first N chars
    text = request_text.strip()
    # Cut at first period/newline if reasonable
    for sep in ('.', '\n', ';'):
        idx = text.find(sep)
        if 10 < idx < max_length:
            text = text[:idx]
            break

    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + "..."

    return text.strip()


def _render_wp_body(
    wp: ChangeWorkPackage,
    request_text: str,
    guardrails: list[str],
    closed_refs: list[str],
    implementation_hint: str,
) -> str:
    """Render full WP markdown including frontmatter and body (T020-T022).

    Args:
        wp: The change work package being rendered
        request_text: Original request text
        guardrails: Acceptance constraints
        closed_refs: Closed WP references for link-only context
        implementation_hint: The spec-kitty implement command hint

    Returns:
        Complete markdown file content
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build frontmatter
    deps_yaml = "\n".join(f'  - "{d}"' for d in wp.dependencies) if wp.dependencies else ""
    closed_refs_yaml = "\n".join(f'  - "{c}"' for c in wp.closed_reference_links) if wp.closed_reference_links else ""

    frontmatter_lines = [
        "---",
        f'work_package_id: "{wp.work_package_id}"',
        f'title: "{wp.title}"',
        f'lane: "{wp.lane}"',
    ]

    if deps_yaml:
        frontmatter_lines.append("dependencies:")
        frontmatter_lines.append(deps_yaml)
    else:
        frontmatter_lines.append("dependencies: []")

    frontmatter_lines.extend([
        f"change_stack: true",
        f'change_request_id: "{wp.change_request_id}"',
        f'change_mode: "{wp.change_mode}"',
        f"stack_rank: {wp.stack_rank}",
        f'review_attention: "{wp.review_attention}"',
    ])

    if closed_refs_yaml:
        frontmatter_lines.append("closed_reference_links:")
        frontmatter_lines.append(closed_refs_yaml)

    frontmatter_lines.extend([
        'assignee: ""',
        'agent: ""',
        'review_status: ""',
        'reviewed_by: ""',
        "history:",
        f'  - timestamp: "{now}"',
        '    lane: "planned"',
        '    agent: "change-command"',
        '    action: "Generated by /spec-kitty.change"',
        "---",
    ])

    # Build body
    body_parts = [
        f"# {wp.work_package_id}: {wp.title}",
        "",
        f"**Implementation command:**",
        "```bash",
        implementation_hint,
        "```",
        "",
        "## Change Request",
        "",
        f"> {request_text}",
        "",
    ]

    # Guardrails (T021)
    if guardrails:
        body_parts.extend([
            "## Acceptance Constraints",
            "",
        ])
        for i, g in enumerate(guardrails, 1):
            body_parts.append(f"{i}. {g}")
        body_parts.append("")

    # Closed references
    if closed_refs:
        body_parts.extend([
            "## Historical Context (Closed References)",
            "",
            "The following closed work packages are referenced for context only (not reopened):",
            "",
        ])
        for ref in closed_refs:
            body_parts.append(f"- {ref}")
        body_parts.append("")

    # Implementation guidance
    body_parts.extend([
        "## Implementation Guidance",
        "",
        "Implement the change described above. Follow the existing codebase patterns.",
        "",
    ])

    # Final testing task (T021 - always present)
    body_parts.extend([
        "## Final Testing Task",
        "",
        "**REQUIRED**: Before marking this WP as done:",
        "",
        "1. Run existing tests to verify no regressions: `pytest tests/`",
        "2. Add tests covering the changes made in this WP",
        "3. Verify all tests pass before moving to `for_review`",
        "",
    ])

    # Activity log
    body_parts.extend([
        "## Activity Log",
        "",
        f"- {now} - change-command - lane=planned - Generated by /spec-kitty.change",
        "",
    ])

    frontmatter = "\n".join(frontmatter_lines)
    body = "\n".join(body_parts)

    return f"{frontmatter}\n\n{body}"


def _build_implementation_hint(wp_id: str, dependencies: list[str]) -> str:
    """Build the spec-kitty implement command hint (T022).

    Args:
        wp_id: Work package ID
        dependencies: List of dependency WP IDs

    Returns:
        The implementation command string
    """
    if dependencies:
        # Use the last dependency as --base (most recent in chain)
        base = dependencies[-1]
        return f"spec-kitty implement {wp_id} --base {base}"
    return f"spec-kitty implement {wp_id}"


def _extract_guardrails(request_text: str) -> list[str]:
    """Extract guardrails/constraints from request text.

    Looks for explicit constraint language in the request. Returns
    a default guardrail if none are found.

    Args:
        request_text: The change request text

    Returns:
        List of guardrail strings
    """
    guardrails: list[str] = []
    text_lower = request_text.lower()

    # Check for "must" / "must not" / "do not" / "never" / "always" patterns
    constraint_patterns = [
        re.compile(r'(?:must|should)\s+(?:not\s+)?(.{10,80}?)(?:\.|$)', re.IGNORECASE),
        re.compile(r'(?:do not|don\'t|never)\s+(.{10,60}?)(?:\.|$)', re.IGNORECASE),
        re.compile(r'(?:always)\s+(.{10,60}?)(?:\.|$)', re.IGNORECASE),
        re.compile(r'(?:without)\s+(.{10,60}?)(?:\.|$)', re.IGNORECASE),
    ]

    for pattern in constraint_patterns:
        for match in pattern.finditer(request_text):
            guardrails.append(match.group(0).strip().rstrip('.'))

    if not guardrails:
        guardrails.append("Ensure existing tests continue to pass")

    return guardrails


def synthesize_change_plan(
    change_req: ChangeRequest,
) -> ChangePlan:
    """Create a change plan from a validated change request (T018).

    Deterministically selects the packaging mode and extracts
    guardrails from the request text.

    Args:
        change_req: Validated change request

    Returns:
        ChangePlan with mode selection and guardrails
    """
    score = change_req.complexity_score
    mode = score.proposed_mode if score is not None else PackagingMode.SINGLE_WP

    # Extract closed references
    closed_refs = (
        change_req.closed_references.closed_wp_ids
        if change_req.closed_references.has_closed_references
        else []
    )

    # Extract guardrails from request text
    guardrails = _extract_guardrails(change_req.raw_text)

    # Determine if merge coordination is needed (integration risk > 0)
    requires_merge = (
        score is not None and score.integration_risk_score > 0
    )

    return ChangePlan(
        request_id=change_req.request_id,
        mode=mode,
        affected_open_wp_ids=[],  # Populated by apply command in WP05
        closed_reference_wp_ids=closed_refs,
        guardrails=guardrails,
        requires_merge_coordination=requires_merge,
    )


def generate_change_work_packages(
    change_req: ChangeRequest,
    plan: ChangePlan,
    tasks_dir: Path,
) -> list[ChangeWorkPackage]:
    """Generate change work packages from a plan (T019-T022).

    Creates one or more WP files based on the packaging mode:
    - single_wp: One WP with all tasks
    - orchestration: One coordinating WP
    - targeted_multi: Multiple focused WPs (2-3 based on scope)

    Args:
        change_req: The validated change request
        plan: The change plan with mode and guardrails
        tasks_dir: Path to the tasks directory for ID allocation

    Returns:
        List of ChangeWorkPackage ready to be written
    """
    score = change_req.complexity_score
    review_att = score.review_attention.value if score is not None else "normal"
    mode_label = _mode_to_frontmatter_label(plan.mode)

    if plan.mode == PackagingMode.TARGETED_MULTI:
        return _generate_targeted_multi(
            change_req, plan, tasks_dir, review_att, mode_label,
        )

    # single_wp and orchestration both produce one WP
    # (orchestration gets a different title prefix)
    wp_id = _next_wp_id(tasks_dir)
    title = _derive_title(change_req.raw_text)
    if plan.mode == PackagingMode.ORCHESTRATION:
        title = f"Orchestrate: {title}"

    slug = _slugify(title)
    filename = f"{wp_id}-{slug}.md"

    hint = _build_implementation_hint(wp_id, [])
    wp = ChangeWorkPackage(
        work_package_id=wp_id,
        title=title,
        filename=filename,
        lane="planned",
        dependencies=[],
        change_stack=True,
        change_request_id=change_req.request_id,
        change_mode=mode_label,
        stack_rank=1,
        review_attention=review_att,
        closed_reference_links=plan.closed_reference_wp_ids,
    )
    wp.body = _render_wp_body(
        wp, change_req.raw_text, plan.guardrails,
        plan.closed_reference_wp_ids, hint,
    )
    return [wp]


def _generate_targeted_multi(
    change_req: ChangeRequest,
    plan: ChangePlan,
    tasks_dir: Path,
    review_att: str,
    mode_label: str,
) -> list[ChangeWorkPackage]:
    """Generate multiple targeted WPs for parallelizable changes.

    Splits the request into 2-3 WPs based on scope breadth score.

    Args:
        change_req: The validated request
        plan: The change plan
        tasks_dir: Path to tasks directory
        review_att: Review attention level
        mode_label: Frontmatter mode label

    Returns:
        List of 2-3 ChangeWorkPackage entries
    """
    score = change_req.complexity_score
    # Determine WP count: 2 for moderate scope, 3 for wide scope
    wp_count = 3 if (score and score.scope_breadth_score >= 3) else 2

    wps: list[ChangeWorkPackage] = []
    base_title = _derive_title(change_req.raw_text, max_length=45)

    for i in range(wp_count):
        wp_id = _next_wp_id(tasks_dir)
        rank = i + 1
        suffix = f"(part {rank}/{wp_count})"
        title = f"{base_title} {suffix}"
        slug = _slugify(title)
        filename = f"{wp_id}-{slug}.md"

        # First WP has no deps, subsequent depend on predecessor
        deps = [wps[i - 1].work_package_id] if i > 0 else []
        hint = _build_implementation_hint(wp_id, deps)

        wp = ChangeWorkPackage(
            work_package_id=wp_id,
            title=title,
            filename=filename,
            lane="planned",
            dependencies=deps,
            change_stack=True,
            change_request_id=change_req.request_id,
            change_mode=mode_label,
            stack_rank=rank,
            review_attention=review_att,
            closed_reference_links=plan.closed_reference_wp_ids if i == 0 else [],
        )
        wp.body = _render_wp_body(
            wp, change_req.raw_text, plan.guardrails,
            plan.closed_reference_wp_ids if i == 0 else [],
            hint,
        )

        # "Create" the file virtually so next _next_wp_id sees it
        # We do this by writing a placeholder (the caller writes the real files)
        # For ID allocation, we track in-memory
        _register_virtual_wp(tasks_dir, wp_id, filename)
        wps.append(wp)

    return wps


# Track virtually allocated WP IDs during multi-WP generation
_virtual_wp_registry: dict[str, set[str]] = {}


def _register_virtual_wp(tasks_dir: Path, wp_id: str, filename: str) -> None:
    """Register a virtual WP file for ID collision avoidance during batch generation."""
    key = str(tasks_dir)
    if key not in _virtual_wp_registry:
        _virtual_wp_registry[key] = set()
    _virtual_wp_registry[key].add(filename)


def _clear_virtual_registry() -> None:
    """Clear the virtual WP registry (call after write is complete)."""
    _virtual_wp_registry.clear()


def _mode_to_frontmatter_label(mode: PackagingMode) -> str:
    """Convert PackagingMode enum to frontmatter label."""
    return {
        PackagingMode.SINGLE_WP: "single",
        PackagingMode.ORCHESTRATION: "orchestration",
        PackagingMode.TARGETED_MULTI: "targeted",
    }[mode]


def write_change_work_packages(
    wps: list[ChangeWorkPackage],
    tasks_dir: Path,
) -> list[Path]:
    """Write generated change work packages to disk.

    Creates the tasks directory if it doesn't exist, then writes
    each WP file.

    Args:
        wps: List of ChangeWorkPackage with rendered bodies
        tasks_dir: Target directory

    Returns:
        List of paths to written files
    """
    tasks_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for wp in wps:
        path = tasks_dir / wp.filename
        path.write_text(wp.body, encoding="utf-8")
        written.append(path)
    _clear_virtual_registry()
    return written


# ============================================================================
# Errors
# ============================================================================


class ChangeStackError(Exception):
    """Error during change stack operations."""
    pass
