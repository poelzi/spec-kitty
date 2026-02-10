"""Deterministic complexity classifier for mid-stream change requests.

Implements a fixed-rubric scoring model (FR-009) with five weighted factors
that sum to a total score of 0-10.  Classification thresholds are hard-coded
and must never use probabilistic or ML-based paths (plan.md constraint).

Thresholds:
    0-3  -> simple   (single change WP)
    4-6  -> complex  (adaptive packaging)
    7-10 -> high     (recommend /spec-kitty.specify, explicit decision required)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# Types
# ============================================================================


class ComplexityClassification(str, Enum):
    """Deterministic complexity classification for a change request."""

    SIMPLE = "simple"
    COMPLEX = "complex"
    HIGH = "high"


class PackagingMode(str, Enum):
    """Adaptive packaging mode selected deterministically from score factors.

    single_wp      - One change WP with multiple tasks (low coupling)
    orchestration  - One coordinating change WP for tightly coupled multi-area changes
    targeted_multi - Multiple focused change WPs (parallelizable)
    """

    SINGLE_WP = "single_wp"
    ORCHESTRATION = "orchestration"
    TARGETED_MULTI = "targeted_multi"


class ReviewAttention(str, Enum):
    """Review attention level for generated change work packages."""

    NORMAL = "normal"
    ELEVATED = "elevated"


# ============================================================================
# Score Component Ranges (fixed weights)
# ============================================================================

#: Maximum values for each scoring factor
SCOPE_BREADTH_MAX = 3
COUPLING_MAX = 2
DEPENDENCY_CHURN_MAX = 2
AMBIGUITY_MAX = 2
INTEGRATION_RISK_MAX = 1
TOTAL_MAX = SCOPE_BREADTH_MAX + COUPLING_MAX + DEPENDENCY_CHURN_MAX + AMBIGUITY_MAX + INTEGRATION_RISK_MAX

#: Classification threshold boundaries
SIMPLE_MAX = 3      # 0-3 inclusive
COMPLEX_MAX = 6     # 4-6 inclusive
# 7-10 -> high


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class ComplexityScore:
    """Full score breakdown for a change request.

    Invariants:
        - total_score == scope_breadth + coupling + dependency_churn + ambiguity + integration_risk
        - recommend_specify == True iff classification == HIGH
    """

    scope_breadth_score: int
    coupling_score: int
    dependency_churn_score: int
    ambiguity_score: int
    integration_risk_score: int
    total_score: int
    classification: ComplexityClassification
    recommend_specify: bool
    proposed_mode: PackagingMode
    review_attention: ReviewAttention

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-friendly dictionary (camelCase keys)."""
        return {
            "scopeBreadthScore": self.scope_breadth_score,
            "couplingScore": self.coupling_score,
            "dependencyChurnScore": self.dependency_churn_score,
            "ambiguityScore": self.ambiguity_score,
            "integrationRiskScore": self.integration_risk_score,
            "totalScore": self.total_score,
            "classification": self.classification.value,
            "recommendSpecify": self.recommend_specify,
            "proposedMode": self.proposed_mode.value,
            "reviewAttention": self.review_attention.value,
        }


# ============================================================================
# Deterministic Scoring Functions
# ============================================================================


def _score_scope_breadth(request_text: str) -> int:
    """Score the scope breadth of a change request (0-3).

    Heuristics (deterministic, no ML):
      0 - Single target: mentions one file/function/class
      1 - Small scope: 2-3 targets or one module-level change
      2 - Medium scope: references multiple modules or directories
      3 - Large scope: cross-cutting ("all", "every", "across") or architectural
    """
    text_lower = request_text.lower()

    # Check for cross-cutting language (score 3)
    cross_cutting = [
        r"\ball\b.*\b(files?|modules?|endpoints?|components?)\b",
        r"\bevery\b.*\b(file|module|endpoint|component)\b",
        r"\bacross\b.*\b(the\s+)?(project|codebase|system|repo)\b",
        r"\barchitectur",
        r"\brefactor.*entire\b",
        r"\bentire\b.*\b(system|codebase|project)\b",
    ]
    for pat in cross_cutting:
        if re.search(pat, text_lower):
            return 3

    # Count distinct target indicators
    target_patterns = [
        # File/path references
        re.compile(r"[a-zA-Z_/]+\.(py|ts|js|md|yaml|yml|json|toml|rs|go|java|rb)\b"),
        # Module/directory references
        re.compile(r"\b(module|package|directory|folder)\s+\w+", re.IGNORECASE),
        # Function/class references
        re.compile(r"\b(function|class|method|endpoint|route|handler|service)\s+\w+", re.IGNORECASE),
    ]

    targets: set[str] = set()
    for pattern in target_patterns:
        for m in pattern.finditer(request_text):
            targets.add(m.group().lower())

    if len(targets) >= 4:
        return 2
    if len(targets) >= 2:
        return 1
    return 0


def _score_coupling(request_text: str) -> int:
    """Score coupling impact (0-2).

    Heuristics:
      0 - Isolated: change to one area with no cross-references
      1 - Moderate: mentions interfaces, shared state, or imports
      2 - High: mentions API contracts, database schema, or multiple integrations
    """
    text_lower = request_text.lower()

    # High coupling indicators (score 2)
    high_coupling = [
        r"\bapi\s+contract",
        r"\bdatabase\s+schema",
        r"\bdb\s+schema",
        r"\bmigration",
        r"\bbreaking\s+change",
        r"\bpublic\s+interface",
        r"\bprotocol\s+buffer",
        r"\bgrpc",
        r"\bgraphql\s+schema",
        r"\bopenapi",
    ]
    for pat in high_coupling:
        if re.search(pat, text_lower):
            return 2

    # Moderate coupling indicators (score 1)
    moderate_coupling = [
        r"\binterface\b",
        r"\bshared\s+(state|config|module|utility)",
        r"\bimport.*from",
        r"\bdependenc",
        r"\bupstream\b",
        r"\bdownstream\b",
        r"\bconsumer",
        r"\bprovider",
    ]
    for pat in moderate_coupling:
        if re.search(pat, text_lower):
            return 1

    return 0


def _score_dependency_churn(request_text: str) -> int:
    """Score dependency churn potential (0-2).

    Heuristics:
      0 - No dependency changes
      1 - Some dependency modification (adding/updating packages, config)
      2 - Major dependency changes (replacing frameworks, major version bumps)
    """
    text_lower = request_text.lower()

    # Major churn (score 2)
    major_churn = [
        r"\breplace\b.*\b(framework|library|orm|database|engine)\b",
        r"\bswitch\b.*\bfrom\b.*\bto\b",
        r"\bmigrate\b.*\bfrom\b.*\bto\b",
        r"\bmajor\s+version",
        r"\brewrite\b.*\bin\b",
        r"\bswap\s+out\b",
    ]
    for pat in major_churn:
        if re.search(pat, text_lower):
            return 2

    # Some churn (score 1)
    some_churn = [
        r"\badd\b.*\b(package|dependency|library|module)\b",
        r"\bupdate\b.*\b(package|dependency|library|version)\b",
        r"\bremove\b.*\b(package|dependency|library)\b",
        r"\binstall\b",
        r"\bnpm\b|\bpip\b|\bcargo\b|\byarn\b",
        r"\bpyproject\.toml\b",
        r"\bpackage\.json\b",
        r"\brequirements\.txt\b",
    ]
    for pat in some_churn:
        if re.search(pat, text_lower):
            return 1

    return 0


def _score_ambiguity(request_text: str) -> int:
    """Score request ambiguity level (0-2).

    Note: This is different from the fail-fast ambiguity check in change_stack.
    That check rejects truly ambiguous requests.  This scores residual
    uncertainty in requests that passed the fail-fast gate.

    Heuristics:
      0 - Clear and specific
      1 - Somewhat vague: uses hedging language or open-ended phrasing
      2 - Very vague: lacks specific targets, uses broad qualitative language
    """
    text_lower = request_text.lower()

    # High ambiguity (score 2)
    high_ambiguity = [
        r"\bimprove\b.*\b(performance|quality|code)\b",
        r"\bclean\s*up\b",
        r"\bmake\s+it\s+(better|nicer|cleaner|faster)\b",
        r"\boptimize\b(?!.*\b(function|method|query|index|cache)\b)",
        r"\brefactor\b(?!.*\b(function|class|method|module|file)\b)",
    ]
    for pat in high_ambiguity:
        if re.search(pat, text_lower):
            return 2

    # Moderate ambiguity (score 1)
    moderate_ambiguity = [
        r"\bmaybe\b",
        r"\bprobably\b",
        r"\bsomething\s+like\b",
        r"\bor\s+something\b",
        r"\bi\s+think\b",
        r"\bpossibly\b",
        r"\bnot\s+sure\b",
        r"\bcould\s+(?:also|maybe)\b",
    ]
    for pat in moderate_ambiguity:
        if re.search(pat, text_lower):
            return 1

    return 0


def _score_integration_risk(request_text: str) -> int:
    """Score integration risk (0-1).

    Heuristics:
      0 - Low risk: localized change
      1 - High risk: touches integration points, CI/CD, deployment, or env config
    """
    text_lower = request_text.lower()

    risk_indicators = [
        r"\bci(/|\s*)cd\b",
        r"\bpipeline\b",
        r"\bdeploy",
        r"\binfrastructur",
        r"\bterraform\b",
        r"\bdocker",
        r"\bkubernetes\b",
        r"\bk8s\b",
        r"\benvironment\s+(variable|config)",
        r"\b\.env\b",
        r"\bsecret",
        r"\bcredential",
        r"\bauth\b.*\b(flow|provider|token)\b",
        r"\bwebhook",
        r"\bexternal\s+(api|service)\b",
    ]
    for pat in risk_indicators:
        if re.search(pat, text_lower):
            return 1

    return 0


# ============================================================================
# Classification and Packaging Mode Selection
# ============================================================================


def _classify(total_score: int) -> ComplexityClassification:
    """Map total score to classification (deterministic thresholds)."""
    if total_score <= SIMPLE_MAX:
        return ComplexityClassification.SIMPLE
    if total_score <= COMPLEX_MAX:
        return ComplexityClassification.COMPLEX
    return ComplexityClassification.HIGH


def _select_packaging_mode(
    classification: ComplexityClassification,
    coupling_score: int,
    scope_breadth_score: int,
) -> PackagingMode:
    """Select adaptive packaging mode deterministically.

    Rules:
      - simple -> always single_wp
      - complex/high with high coupling (>=2) -> orchestration
      - complex/high with scope_breadth >= 2 and coupling < 2 -> targeted_multi
      - complex/high otherwise -> single_wp
    """
    if classification == ComplexityClassification.SIMPLE:
        return PackagingMode.SINGLE_WP

    if coupling_score >= 2:
        return PackagingMode.ORCHESTRATION

    if scope_breadth_score >= 2:
        return PackagingMode.TARGETED_MULTI

    return PackagingMode.SINGLE_WP


# ============================================================================
# Public API
# ============================================================================


def classify_change_request(
    request_text: str,
    continued_after_warning: bool = False,
) -> ComplexityScore:
    """Classify a change request using the deterministic rubric.

    This is a pure function: given the same input, it always produces the
    same output.  No randomness, no external state, no ML models.

    Args:
        request_text: Natural-language change request text
        continued_after_warning: True if user explicitly chose to continue
            past a high-complexity warning (sets elevated review attention)

    Returns:
        ComplexityScore with full breakdown and classification
    """
    scope_breadth = _score_scope_breadth(request_text)
    coupling = _score_coupling(request_text)
    dependency_churn = _score_dependency_churn(request_text)
    ambiguity = _score_ambiguity(request_text)
    integration_risk = _score_integration_risk(request_text)

    total = scope_breadth + coupling + dependency_churn + ambiguity + integration_risk
    classification = _classify(total)
    recommend_specify = classification == ComplexityClassification.HIGH
    proposed_mode = _select_packaging_mode(classification, coupling, scope_breadth)

    # FR-011: elevated review attention when continuing after warning
    if continued_after_warning and classification == ComplexityClassification.HIGH:
        review_attention = ReviewAttention.ELEVATED
    else:
        review_attention = ReviewAttention.NORMAL

    return ComplexityScore(
        scope_breadth_score=scope_breadth,
        coupling_score=coupling,
        dependency_churn_score=dependency_churn,
        ambiguity_score=ambiguity,
        integration_risk_score=integration_risk,
        total_score=total,
        classification=classification,
        recommend_specify=recommend_specify,
        proposed_mode=proposed_mode,
        review_attention=review_attention,
    )
