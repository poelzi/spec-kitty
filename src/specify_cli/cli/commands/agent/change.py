"""Agent change commands - programmatic endpoints for mid-stream change requests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from specify_cli.core.feature_detection import (
    FeatureDetectionError,
    detect_feature_slug,
)
from specify_cli.tasks_support import TaskCliError, find_repo_root

app = typer.Typer(
    name="change",
    help="Mid-stream change request commands for AI agents",
    no_args_is_help=True,
)


def _output_result(data: dict[str, object], as_json: bool) -> None:
    """Output result as JSON or human-readable text."""
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        for key, value in data.items():
            print(f"  {key}: {value}")


def _output_error(error: str, message: str, as_json: bool) -> None:
    """Output error as JSON or human-readable text."""
    if as_json:
        print(json.dumps({"error": error, "message": message}))
    else:
        print(f"Error: {error} - {message}")


def _resolve_feature(feature: Optional[str]) -> tuple[Path, str]:
    """Resolve repo root and feature slug.

    Returns:
        Tuple of (repo_root, feature_slug)

    Raises:
        typer.Exit: If resolution fails
    """
    try:
        repo_root = find_repo_root()
    except TaskCliError as exc:
        print(f"Error: {exc}")
        raise typer.Exit(1)

    try:
        feature_slug = (feature or detect_feature_slug(repo_root, cwd=Path.cwd())).strip()
    except (FeatureDetectionError, Exception) as exc:
        print(f"Error: Could not detect feature - {exc}")
        raise typer.Exit(1)

    return repo_root, feature_slug


@app.command(name="preview")
def preview(
    request_text: Annotated[str, typer.Argument(help="Natural-language change request")],
    feature: Annotated[Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")] = None,
    submitted_by: Annotated[str, typer.Option("--submitted-by", help="Who submitted the request")] = "agent",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Validate and classify a change request before creating work packages.

    Performs branch stash routing, complexity assessment, and ambiguity
    detection without writing any files. Returns a preview of the planned
    changes for confirmation.

    Examples:
        spec-kitty agent change preview "use SQLAlchemy instead of raw SQL"
        spec-kitty agent change preview "add caching" --json
    """
    repo_root, feature_slug = _resolve_feature(feature)

    # Stubbed response - actual implementation in WP02-WP04
    result: dict[str, object] = {
        "requestId": "stub-preview-id",
        "stashKey": feature_slug,
        "stashScope": "feature",
        "stashPath": str(repo_root / "kitty-specs" / feature_slug / "tasks"),
        "validationState": "valid",
        "complexity": {
            "scopeBreadthScore": 0,
            "couplingScore": 0,
            "dependencyChurnScore": 0,
            "ambiguityScore": 0,
            "integrationRiskScore": 0,
            "totalScore": 0,
            "classification": "simple",
            "recommendSpecify": False,
        },
        "proposedMode": "single_wp",
        "warningRequired": False,
        "warningMessage": None,
        "requiresClarification": False,
        "clarificationPrompt": None,
        "status": "stubbed",
        "message": "Preview endpoint registered. Full implementation in WP02-WP04.",
    }

    _output_result(result, json_output)


@app.command(name="apply")
def apply(
    request_id: Annotated[str, typer.Argument(help="Request ID from preview step")],
    feature: Annotated[Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")] = None,
    continue_after_warning: Annotated[bool, typer.Option("--continue", help="Continue despite complexity warning")] = False,
    confirm_unambiguous: Annotated[bool, typer.Option("--confirm", help="Confirm request is unambiguous")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Apply a validated change request and create change work packages.

    Takes a request ID from the preview step and creates the actual work
    package files with dependencies, documentation links, and merge
    coordination jobs.

    Examples:
        spec-kitty agent change apply "preview-id-123"
        spec-kitty agent change apply "preview-id-123" --continue --json
    """
    repo_root, feature_slug = _resolve_feature(feature)

    # Stubbed response - actual implementation in WP04-WP06
    result: dict[str, object] = {
        "requestId": request_id,
        "createdWorkPackages": [],
        "closedReferenceLinks": [],
        "mergeCoordinationJobs": [],
        "consistency": {
            "updatedTasksDoc": False,
            "dependencyValidationPassed": True,
            "brokenLinksFixed": 0,
            "issues": [],
        },
        "status": "stubbed",
        "message": "Apply endpoint registered. Full implementation in WP04-WP06.",
    }

    _output_result(result, json_output)


@app.command(name="next")
def next_doable(
    feature: Annotated[Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Resolve the next doable work package with change-stack priority.

    Implements stack-first selection: ready change-stack items take priority
    over normal backlog items. If change-stack items exist but none are
    ready, normal progression is blocked and blockers are reported.

    Examples:
        spec-kitty agent change next
        spec-kitty agent change next --json
    """
    repo_root, feature_slug = _resolve_feature(feature)

    # Stubbed response - actual implementation in WP07
    result: dict[str, object] = {
        "stashKey": feature_slug,
        "selectedSource": "normal_backlog",
        "nextWorkPackageId": None,
        "normalProgressionBlocked": False,
        "blockers": [],
        "status": "stubbed",
        "message": "Next-doable endpoint registered. Full implementation in WP07.",
    }

    _output_result(result, json_output)


@app.command(name="reconcile")
def reconcile(
    feature: Annotated[Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")] = None,
    recompute_merge_jobs: Annotated[bool, typer.Option("--recompute-merge-jobs", help="Recompute merge coordination jobs")] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Recompute links, dependencies, and merge coordination jobs.

    Validates all change-stack references, repairs broken links, and
    regenerates merge coordination jobs where integration risk exists.

    Examples:
        spec-kitty agent change reconcile
        spec-kitty agent change reconcile --json
    """
    repo_root, feature_slug = _resolve_feature(feature)

    # Stubbed response - actual implementation in WP06
    result: dict[str, object] = {
        "stashKey": feature_slug,
        "consistency": {
            "updatedTasksDoc": False,
            "dependencyValidationPassed": True,
            "brokenLinksFixed": 0,
            "issues": [],
        },
        "mergeCoordinationJobs": [],
        "status": "stubbed",
        "message": "Reconcile endpoint registered. Full implementation in WP06.",
    }

    _output_result(result, json_output)


__all__ = ["app"]
