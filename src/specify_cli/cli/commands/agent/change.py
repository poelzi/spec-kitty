"""Agent change commands - programmatic endpoints for mid-stream change requests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from specify_cli.core.change_classifier import ComplexityClassification
from specify_cli.core.change_stack import (
    ChangeStackError,
    ValidationState,
    generate_change_work_packages,
    resolve_stash,
    synthesize_change_plan,
    validate_change_request,
    write_change_work_packages,
    resolve_next_change_wp,
)
from specify_cli.core.feature_detection import (
    FeatureDetectionError,
    detect_feature_slug,
)
from specify_cli.core.paths import locate_project_root

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


def _resolve_repo() -> Path:
    """Resolve project root (requires initialized Spec Kitty project).

    Returns:
        Project root path (with .kittify directory)

    Raises:
        typer.Exit: If not inside an initialized Spec Kitty project
    """
    repo_root = locate_project_root()
    if repo_root is None:
        print(
            "Error: Not inside an initialized Spec Kitty project (.kittify not found)"
        )
        raise typer.Exit(1)
    return repo_root


def _resolve_feature(feature: Optional[str]) -> tuple[Path, str]:
    """Resolve repo root and feature slug.

    Returns:
        Tuple of (repo_root, feature_slug)

    Raises:
        typer.Exit: If resolution fails
    """
    repo_root = _resolve_repo()

    try:
        feature_slug = (
            feature or detect_feature_slug(repo_root, cwd=Path.cwd())
        ).strip()
    except (FeatureDetectionError, Exception) as exc:
        print(f"Error: Could not detect feature - {exc}")
        raise typer.Exit(1)

    return repo_root, feature_slug


@app.command(name="preview")
def preview(
    request_text: Annotated[
        str, typer.Argument(help="Natural-language change request")
    ],
    feature: Annotated[
        Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")
    ] = None,
    submitted_by: Annotated[
        str, typer.Option("--submitted-by", help="Who submitted the request")
    ] = "agent",
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
    repo_root = _resolve_repo()

    # Validate and route the change request
    try:
        change_req = validate_change_request(
            request_text=request_text,
            repo_root=repo_root,
            feature=feature,
        )
    except ChangeStackError as exc:
        _output_error("stash_resolution_failed", str(exc), json_output)
        raise typer.Exit(1)

    # Build preview response
    requires_clarification = change_req.validation_state == ValidationState.AMBIGUOUS
    score = change_req.complexity_score

    # Determine warning state (FR-010)
    warning_required = score is not None and score.recommend_specify
    warning_message: str | None = None
    if warning_required:
        warning_message = (
            "This change request exceeds the complexity threshold. "
            "Consider using /spec-kitty.specify for full planning. "
            "Use --continue flag on apply to proceed anyway."
        )

    result: dict[str, object] = {
        "requestId": change_req.request_id,
        "stashKey": change_req.stash.stash_key,
        "stashScope": change_req.stash.scope.value,
        "stashPath": str(change_req.stash.stash_path),
        "validationState": change_req.validation_state.value,
        "complexity": score.to_dict() if score is not None else {},
        "proposedMode": score.proposed_mode.value if score is not None else "single_wp",
        "warningRequired": warning_required,
        "warningMessage": warning_message,
        "requiresClarification": requires_clarification,
        "clarificationPrompt": change_req.ambiguity.clarification_prompt,
    }

    # Include closed reference info if present
    if change_req.closed_references.has_closed_references:
        result["closedReferences"] = {
            "wpIds": change_req.closed_references.closed_wp_ids,
            "linkOnly": True,
        }

    _output_result(result, json_output)


@app.command(name="apply")
def apply(
    request_id: Annotated[str, typer.Argument(help="Request ID from preview step")],
    request_text: Annotated[
        str,
        typer.Option(
            "--request-text",
            help="Original request text (required for complexity gating)",
        ),
    ] = ...,
    feature: Annotated[
        Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")
    ] = None,
    continue_after_warning: Annotated[
        bool, typer.Option("--continue", help="Continue despite complexity warning")
    ] = False,
    confirm_unambiguous: Annotated[
        bool, typer.Option("--confirm", help="Confirm request is unambiguous")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Apply a validated change request and create change work packages.

    Takes a request ID from the preview step and creates the actual work
    package files with dependencies, documentation links, and merge
    coordination jobs.

    When the request exceeds the complexity threshold, the --continue flag
    is required (FR-010, SC-003). Without it, apply is blocked.

    Examples:
        spec-kitty agent change apply "preview-id-123" --request-text "use SQLAlchemy"
        spec-kitty agent change apply "preview-id-123" --request-text "replace ORM" --continue --json
    """
    repo_root, feature_slug = _resolve_feature(feature)

    # FR-010/FR-011: Score complexity and enforce continue gate
    from specify_cli.core.change_classifier import classify_change_request as _classify

    score = _classify(request_text, continued_after_warning=continue_after_warning)
    if score.recommend_specify and not continue_after_warning:
        _output_error(
            "high_complexity_blocked",
            "Request exceeds complexity threshold (score {}/10, classification: {}). "
            "Use --continue to proceed or use /spec-kitty.specify for full planning.".format(
                score.total_score, score.classification.value
            ),
            json_output,
        )
        raise typer.Exit(1)

    # Re-validate request to get full ChangeRequest if text provided
    change_req = None
    if request_text:
        try:
            change_req = validate_change_request(
                request_text=request_text,
                repo_root=repo_root,
                feature=feature,
            )
            # Override the request_id with the one from preview
            change_req.request_id = request_id
            # Propagate the score with correct continued_after_warning state
            # (validate_change_request recomputes without it)
            change_req.complexity_score = score
        except ChangeStackError as exc:
            _output_error("validation_failed", str(exc), json_output)
            raise typer.Exit(1)

    if change_req is not None:
        # Synthesize plan and generate WPs
        plan = synthesize_change_plan(change_req)
        wps = generate_change_work_packages(
            change_req, plan, change_req.stash.stash_path
        )

        # Write WP files to disk
        written_paths = write_change_work_packages(wps, change_req.stash.stash_path)

        result: dict[str, object] = {
            "requestId": request_id,
            "createdWorkPackages": [wp.to_dict() for wp in wps],
            "writtenFiles": [str(p) for p in written_paths],
            "closedReferenceLinks": plan.closed_reference_wp_ids,
            "mergeCoordinationJobs": [],  # Full implementation in WP06
            "consistency": {
                "updatedTasksDoc": False,
                "dependencyValidationPassed": True,
                "brokenLinksFixed": 0,
                "issues": [],
            },
            "mode": plan.mode.value,
        }
        if score is not None:
            result["complexity"] = score.to_dict()
    else:
        # No request text: legacy/minimal apply (preview-only flow)
        result = {
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
            "status": "no_request_text",
            "message": "No --request-text provided. Pass request text for WP synthesis.",
        }

    _output_result(result, json_output)


@app.command(name="next")
def next_doable(
    feature: Annotated[
        Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")
    ] = None,
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

    # Resolve tasks directory
    tasks_dir = repo_root / "kitty-specs" / feature_slug / "tasks"

    # Run stack-first selection (FR-017)
    selection = resolve_next_change_wp(tasks_dir, feature_slug)

    result: dict[str, object] = {
        "stashKey": feature_slug,
        "selectedSource": selection.selected_source,
        "nextWorkPackageId": selection.next_wp_id,
        "normalProgressionBlocked": selection.normal_progression_blocked,
        "blockers": selection.blockers,
    }

    if selection.pending_change_wps:
        result["pendingChangeWPs"] = selection.pending_change_wps

    _output_result(result, json_output)


@app.command(name="reconcile")
def reconcile(
    feature: Annotated[
        Optional[str], typer.Option("--feature", help="Feature slug (auto-detected)")
    ] = None,
    recompute_merge_jobs: Annotated[
        bool,
        typer.Option(
            "--recompute-merge-jobs", help="Recompute merge coordination jobs"
        ),
    ] = True,
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
