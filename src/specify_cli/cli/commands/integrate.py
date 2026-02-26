"""Integrate command: merge a feature's landing branch into the upstream branch.

This command is the second step in the landing branch workflow:
1. `spec-kitty merge` - merges WP branches into the feature's landing branch
2. `spec-kitty integrate` - merges the landing branch into upstream (e.g., main)

The landing branch is NEVER deleted by this command. It remains available
for future changes, upstream PR submission, and rebasing.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import typer

from specify_cli.cli import StepTracker
from specify_cli.cli.helpers import check_version_compatibility, console, show_banner
from specify_cli.core.context_validation import require_main_repo
from specify_cli.core.feature_detection import (
    get_feature_target_branch,
    get_feature_upstream_branch,
)
from specify_cli.core.git_ops import has_remote, has_tracking_branch, run_command
from specify_cli.core.spec_merge_safety import (
    get_spec_path_exclusion_patterns,
    should_exclude_from_merge,
)
from specify_cli.tasks_support import TaskCliError, find_repo_root


def _get_main_repo_root(repo_root: Path) -> Path:
    """Get the main repository root, even if called from a worktree."""
    git_dir = repo_root / ".git"
    if git_dir.is_dir():
        return repo_root
    if git_dir.is_file():
        content = git_dir.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir:"):
            gitdir_path = Path(content[len("gitdir:") :].strip()).resolve()
            main_git_dir = gitdir_path
            while main_git_dir.name != ".git":
                main_git_dir = main_git_dir.parent
                if main_git_dir == main_git_dir.parent:
                    break
            return main_git_dir.parent
    return repo_root


def _detect_feature_slug(repo_root: Path) -> str | None:
    """Detect feature slug from current branch or worktree context."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    branch = result.stdout.strip()

    # Try WP branch pattern first: 010-feature-WP01 -> 010-feature
    wp_match = re.match(r"(.*?)-WP\d{2}$", branch)
    if wp_match:
        return wp_match.group(1)

    # Try feature branch pattern: 010-feature-name
    feature_match = re.match(r"^\d{3}-.+$", branch)
    if feature_match:
        return branch

    return None


def _remove_spec_paths_from_staging(repo_root: Path) -> int:
    """Remove spec storage paths from git staging area before commit.

    Used after ``git merge --squash`` to prevent spec storage files from
    being included in the squash commit.  This is the pre-commit variant
    of spec path exclusion.

    Returns the number of files unstaged.
    """
    exclusion_patterns = get_spec_path_exclusion_patterns(repo_root)
    if not exclusion_patterns:
        return 0

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0

    staged_files = result.stdout.strip().splitlines()
    spec_files = [
        f for f in staged_files
        if should_exclude_from_merge(f, exclusion_patterns)
    ]

    if not spec_files:
        return 0

    # Unstage spec files so they are not included in the commit
    for spec_file in spec_files:
        subprocess.run(
            ["git", "reset", "HEAD", "--", spec_file],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        # Also revert the working tree copy
        subprocess.run(
            ["git", "checkout", "HEAD", "--", spec_file],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )

    if spec_files:
        console.print(
            f"[cyan]→ Excluded {len(spec_files)} spec storage file(s) from integration[/cyan]"
        )

    return len(spec_files)


def _remove_spec_paths_post_merge(repo_root: Path, feature_slug: str) -> int:
    """Remove spec storage files introduced by a non-squash merge.

    After a ``git merge --no-ff``, any spec files from the landing branch
    are already committed.  This function checks if any spec files were
    added and creates a follow-up commit to remove them.

    Returns the number of files removed.
    """
    exclusion_patterns = get_spec_path_exclusion_patterns(repo_root)
    if not exclusion_patterns:
        return 0

    # Check for spec files that were added/modified in the merge commit
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1..HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0

    changed_files = result.stdout.strip().splitlines()
    spec_files = [
        f for f in changed_files
        if should_exclude_from_merge(f, exclusion_patterns)
    ]

    if not spec_files:
        return 0

    # Remove spec files from the working tree and stage removals
    for spec_file in spec_files:
        file_path = repo_root / spec_file
        if file_path.exists():
            subprocess.run(
                ["git", "rm", "-f", "--", spec_file],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )

    # Commit the removals
    subprocess.run(
        [
            "git", "commit", "-m",
            f"chore: remove spec storage files from {feature_slug} integration",
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )

    console.print(
        f"[cyan]→ Removed {len(spec_files)} stale spec storage file(s) from upstream[/cyan]"
    )

    return len(spec_files)


@require_main_repo
def integrate(
    feature: str = typer.Option(
        None, "--feature", help="Feature slug (auto-detected from current branch)"
    ),
    push: bool = typer.Option(
        False, "--push", help="Push upstream branch to origin after integrating"
    ),
    strategy: str = typer.Option(
        "merge", "--strategy", help="Integration strategy: merge or squash"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
) -> None:
    """Merge a feature's landing branch into the upstream branch (e.g., main).

    This is for local integration after WP branches have been merged into the
    landing branch via `spec-kitty merge`. The landing branch is NEVER deleted
    by this command - it remains available for upstream PR submission and future
    changes.

    The upstream branch is determined from meta.json's upstream_branch field
    (defaults to "main").

    Examples:
        # Integrate current feature into main
        spec-kitty integrate

        # Integrate a specific feature
        spec-kitty integrate --feature 010-my-feature

        # Squash and push
        spec-kitty integrate --strategy squash --push

        # Preview without executing
        spec-kitty integrate --dry-run
    """
    show_banner()

    tracker = StepTracker("Feature Integration")
    tracker.add("detect", "Detect feature and branches")
    tracker.add("checkout", "Switch to upstream branch")
    tracker.add("pull", "Update upstream branch")
    tracker.add("merge", "Merge landing branch")
    if push:
        tracker.add("push", "Push to origin")
    console.print()

    try:
        repo_root = find_repo_root()
    except TaskCliError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    check_version_compatibility(repo_root, "integrate")
    main_repo = _get_main_repo_root(repo_root)

    # Step 1: Detect feature slug
    tracker.start("detect")
    feature_slug = feature
    if not feature_slug:
        feature_slug = _detect_feature_slug(main_repo)
        if not feature_slug:
            tracker.error("detect", "could not detect feature")
            console.print(tracker.render())
            console.print(
                "\n[red]Error:[/red] Could not detect feature from current branch."
            )
            console.print("Use --feature <slug> to specify the feature to integrate.")
            raise typer.Exit(1)

    # Resolve landing branch and upstream branch from meta.json
    landing_branch = get_feature_target_branch(main_repo, feature_slug)
    upstream_branch = get_feature_upstream_branch(main_repo, feature_slug)

    # Validate landing branch exists
    landing_exists = (
        subprocess.run(
            ["git", "rev-parse", "--verify", landing_branch],
            cwd=main_repo,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )

    if not landing_exists:
        tracker.error("detect", f"landing branch '{landing_branch}' not found")
        console.print(tracker.render())
        console.print(
            f"\n[red]Error:[/red] Landing branch '{landing_branch}' does not exist."
        )
        console.print(
            "Run `spec-kitty merge` first to merge WP branches into the landing branch."
        )
        raise typer.Exit(1)

    # Validate upstream branch exists
    upstream_exists = (
        subprocess.run(
            ["git", "rev-parse", "--verify", upstream_branch],
            cwd=main_repo,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )

    if not upstream_exists:
        tracker.error("detect", f"upstream branch '{upstream_branch}' not found")
        console.print(tracker.render())
        console.print(
            f"\n[red]Error:[/red] Upstream branch '{upstream_branch}' does not exist."
        )
        raise typer.Exit(1)

    tracker.complete("detect", f"{landing_branch} -> {upstream_branch}")
    console.print(f"[cyan]Feature:[/cyan] {feature_slug}")
    console.print(f"[cyan]Landing branch:[/cyan] {landing_branch}")
    console.print(f"[cyan]Upstream branch:[/cyan] {upstream_branch}")

    # Dry run
    if dry_run:
        console.print(tracker.render())
        console.print("\n[cyan]Dry run - would execute:[/cyan]")
        steps = [
            f"git checkout {upstream_branch}",
            "git pull --ff-only",
        ]
        if strategy == "squash":
            steps.extend(
                [
                    f"git merge --squash {landing_branch}",
                    f"git commit -m 'Integrate {feature_slug}'",
                ]
            )
        else:
            steps.append(
                f"git merge --no-ff {landing_branch} -m 'Integrate {feature_slug}'"
            )
        if push:
            steps.append(f"git push origin {upstream_branch}")
        steps.append(
            f"# Landing branch '{landing_branch}' is preserved (never deleted)"
        )
        for idx, step in enumerate(steps, start=1):
            console.print(f"  {idx}. {step}")
        return

    # Step 2: Checkout upstream branch
    tracker.start("checkout")
    try:
        os.chdir(main_repo)
        _, status_output, _ = run_command(
            ["git", "status", "--porcelain"], capture=True
        )
        if status_output.strip():
            raise RuntimeError(f"Repository at {main_repo} has uncommitted changes.")
        run_command(["git", "checkout", upstream_branch])
        tracker.complete("checkout", f"on {upstream_branch}")
    except Exception as exc:
        tracker.error("checkout", str(exc))
        console.print(tracker.render())
        raise typer.Exit(1)

    # Step 3: Pull latest
    tracker.start("pull")
    try:
        if not has_remote(main_repo):
            tracker.skip("pull", "no remote configured")
        elif not has_tracking_branch(main_repo):
            tracker.skip("pull", "no upstream tracking")
        else:
            run_command(["git", "pull", "--ff-only"])
            tracker.complete("pull")
    except Exception as exc:
        tracker.error("pull", str(exc))
        console.print(tracker.render())
        console.print(
            f"\n[yellow]Warning:[/yellow] Could not fast-forward {upstream_branch}."
        )
        console.print("You may need to resolve conflicts manually.")
        raise typer.Exit(1)

    # Step 4: Merge landing branch into upstream
    tracker.start("merge")
    try:
        if strategy == "squash":
            run_command(["git", "merge", "--squash", landing_branch])
            # Remove spec storage paths before committing (merge safety)
            _remove_spec_paths_from_staging(repo_root)
            run_command(["git", "commit", "-m", f"Integrate {feature_slug}"])
            tracker.complete("merge", "squashed")
        else:
            run_command(
                [
                    "git",
                    "merge",
                    "--no-ff",
                    landing_branch,
                    "-m",
                    f"Integrate {feature_slug}",
                ]
            )
            # After a non-squash merge, spec files may have been introduced.
            # Create a follow-up commit to remove them if needed.
            _remove_spec_paths_post_merge(repo_root, feature_slug)
            tracker.complete("merge", "merged with merge commit")
    except Exception as exc:
        tracker.error("merge", str(exc))
        console.print(tracker.render())
        console.print(
            f"\n[red]Integration failed.[/red] Resolve conflicts and try again."
        )
        raise typer.Exit(1)

    # Step 5: Push if requested
    if push:
        tracker.start("push")
        try:
            run_command(["git", "push", "origin", upstream_branch])
            tracker.complete("push")
        except Exception as exc:
            tracker.error("push", str(exc))
            console.print(tracker.render())
            console.print(
                f"\n[yellow]Warning:[/yellow] Integration succeeded but push failed."
            )
            console.print(f"Run manually: git push origin {upstream_branch}")

    console.print(tracker.render())
    console.print(
        f"\n[bold green]✓ Feature {feature_slug} integrated into {upstream_branch}[/bold green]"
    )
    console.print(
        f"[dim]Landing branch '{landing_branch}' preserved for upstream PR and future changes[/dim]"
    )


__all__ = ["integrate"]
