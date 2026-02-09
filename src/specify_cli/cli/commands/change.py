"""Change command - capture mid-implementation review requests as work packages."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from specify_cli.cli import StepTracker
from specify_cli.cli.helpers import check_version_compatibility, get_project_root_or_exit, show_banner
from specify_cli.core.feature_detection import (
    FeatureDetectionError,
    detect_feature_slug,
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
    tracker.add("feature", "Resolve feature context")
    tracker.add("validate", "Validate change request")
    tracker.add("assess", "Assess complexity")
    tracker.add("plan", "Plan work packages")
    console.print()

    # Step 1: Locate project
    tracker.start("project")
    tracker.complete("project", str(project_root))

    # Step 2: Resolve feature context
    tracker.start("feature")
    try:
        feature_slug = (feature or detect_feature_slug(repo_root, cwd=Path.cwd())).strip()
    except (FeatureDetectionError, Exception) as exc:
        tracker.error("feature", str(exc))
        console.print(tracker.render())
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    tracker.complete("feature", feature_slug)

    # Step 3-5: Stubbed for WP01 - actual implementation in later WPs
    tracker.start("validate")
    if not request:
        tracker.error("validate", "No change request provided")
        console.print(tracker.render())
        console.print()
        console.print("[yellow]Usage:[/yellow]")
        console.print('  spec-kitty change "your change request here"')
        console.print()
        console.print("[dim]Interactive mode not yet implemented.[/dim]")
        raise typer.Exit(1)
    tracker.complete("validate", "Request accepted")

    tracker.start("assess")
    tracker.complete("assess", "Stubbed (WP03)")

    tracker.start("plan")
    tracker.complete("plan", "Stubbed (WP04)")

    console.print(tracker.render())
    console.print()
    console.print("[yellow]Note:[/yellow] Change command surface registered.")
    console.print("[dim]Full implementation (classification, synthesis, dependency linking)")
    console.print("will be added in subsequent work packages (WP02-WP08).[/dim]")


__all__ = ["change"]
