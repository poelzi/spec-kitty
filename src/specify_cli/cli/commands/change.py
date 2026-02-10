"""Change command - capture mid-implementation review requests as work packages."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from specify_cli.cli import StepTracker
from specify_cli.cli.helpers import check_version_compatibility, get_project_root_or_exit, show_banner
from specify_cli.core.change_classifier import ComplexityClassification
from specify_cli.core.change_stack import (
    ChangeStackError,
    ValidationState,
    validate_change_request,
)
from specify_cli.tasks_support import TaskCliError, find_repo_root


console = Console()


def change(
    request: Optional[str] = typer.Argument(None, help="Change request description (interactive if omitted)"),
    feature: Optional[str] = typer.Option(None, "--feature", help="Feature slug to target (auto-detected when omitted)"),
    json_output: Optional[str] = typer.Option(None, "--json", help="Write JSON output to this path"),
    preview: bool = typer.Option(False, "--preview", help="Preview change plan without applying"),
) -> None:
    """Capture a mid-implementation change request and create work packages.

    Analyzes the change request, assesses complexity, and generates one or
    more work packages with correct dependencies and documentation links.

    Examples:
        # Interactive mode (prompted for request)
        spec-kitty change

        # Direct request
        spec-kitty change "use SQLAlchemy instead of raw SQL"

        # Preview without creating WPs
        spec-kitty change "refactor auth module" --preview

        # JSON output for automation
        spec-kitty change "add caching layer" --json output.json
    """
    show_banner()

    try:
        repo_root = find_repo_root()
    except TaskCliError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    project_root = get_project_root_or_exit(repo_root)
    check_version_compatibility(project_root, "change")

    tracker = StepTracker("Change Request")
    tracker.add("project", "Locate project root")
    tracker.add("route", "Resolve branch stash")
    tracker.add("validate", "Validate change request")
    tracker.add("assess", "Assess complexity")
    tracker.add("plan", "Plan work packages")
    console.print()

    # Step 1: Locate project
    tracker.start("project")
    tracker.complete("project", str(project_root))

    # Step 2: Resolve branch stash and validate request
    tracker.start("route")
    if not request:
        tracker.error("route", "No change request provided")
        console.print(tracker.render())
        console.print()
        console.print("[yellow]Usage:[/yellow]")
        console.print('  spec-kitty change "your change request here"')
        console.print()
        console.print("[dim]Interactive mode not yet implemented.[/dim]")
        raise typer.Exit(1)

    try:
        change_req = validate_change_request(
            request_text=request,
            repo_root=repo_root,
            feature=feature,
        )
    except ChangeStackError as exc:
        tracker.error("route", str(exc))
        console.print(tracker.render())
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    tracker.complete("route", f"{change_req.stash.scope.value}: {change_req.stash.stash_key}")

    # Step 3: Validate - check ambiguity (fail-fast per FR-002A)
    tracker.start("validate")
    if change_req.validation_state == ValidationState.AMBIGUOUS:
        tracker.error("validate", "Ambiguous request - clarification needed")
        console.print(tracker.render())
        console.print()
        console.print("[red]Error:[/red] Change request is ambiguous.")
        if change_req.ambiguity.clarification_prompt:
            console.print()
            console.print(change_req.ambiguity.clarification_prompt)
        raise typer.Exit(1)

    # Report closed references (link-only, FR-016)
    if change_req.closed_references.has_closed_references:
        closed_ids = ", ".join(change_req.closed_references.closed_wp_ids)
        console.print(f"[yellow]Note:[/yellow] Request references closed WP(s): {closed_ids}")
        console.print("[dim]These will be linked as historical context (not reopened).[/dim]")

    tracker.complete("validate", "Request validated")

    # Step 4: Complexity assessment (FR-009, FR-010)
    tracker.start("assess")
    score = change_req.complexity_score
    if score is None:
        tracker.error("assess", "Scoring failed")
        console.print(tracker.render())
        raise typer.Exit(1)

    tracker.complete(
        "assess",
        f"{score.classification.value} (score {score.total_score}/10)",
    )

    # FR-010: High complexity warning with recommend /spec-kitty.specify
    if score.recommend_specify:
        console.print()
        console.print(
            "[yellow]Warning:[/yellow] This change request exceeds the "
            "complexity threshold (score {}/{}).".format(score.total_score, 10)
        )
        console.print(
            "[yellow]Recommendation:[/yellow] Use [bold]/spec-kitty.specify[/bold] "
            "for full planning."
        )
        console.print()
        console.print("Score breakdown:")
        console.print(f"  Scope breadth:    {score.scope_breadth_score}/3")
        console.print(f"  Coupling impact:  {score.coupling_score}/2")
        console.print(f"  Dependency churn: {score.dependency_churn_score}/2")
        console.print(f"  Ambiguity:        {score.ambiguity_score}/2")
        console.print(f"  Integration risk: {score.integration_risk_score}/1")
        console.print(f"  [bold]Total:            {score.total_score}/10[/bold]")
        console.print()
        console.print(
            "To continue anyway, use: "
            "[bold]spec-kitty agent change apply <request-id> --continue[/bold]"
        )

    # Step 5: Plan work packages (stubbed for WP04)
    tracker.start("plan")
    tracker.complete("plan", f"Mode: {score.proposed_mode.value} (WP04 for full synthesis)")

    console.print(tracker.render())

    if preview:
        console.print()
        console.print("[cyan]Preview mode:[/cyan] No work packages created.")
        console.print(f"  Stash: {change_req.stash.stash_path}")
        console.print(f"  Scope: {change_req.stash.scope.value}")
        console.print(f"  Request ID: {change_req.request_id}")
        console.print(f"  Complexity: {score.classification.value} ({score.total_score}/10)")
        console.print(f"  Packaging: {score.proposed_mode.value}")


__all__ = ["change"]
