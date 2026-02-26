from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skip(reason="Needs rework after 1.0.0 merge - planning artifact commit flow changed")
def test_workflow_implement_branches_from_landing_branch(
    test_project: Path, run_cli
) -> None:
    """workflow implement must base new WP worktrees on landing branch.

    Regression coverage for cases where workflow implement created worktrees from
    the currently checked-out planning branch instead of the feature landing
    branch, causing branch ancestry drift.
    """
    repo = test_project

    # Create an explicit base/planning branch to simulate "start from another
    # feature landing" requests.
    assert _git(repo, "checkout", "-b", "001-otel-landing").returncode == 0
    (repo / "otel-baseline.txt").write_text("otel baseline\n", encoding="utf-8")
    assert _git(repo, "add", "otel-baseline.txt").returncode == 0
    assert _git(repo, "commit", "-m", "Add otel baseline marker").returncode == 0
    assert _git(repo, "checkout", "main").returncode == 0

    # Create feature with explicit upstream/base branch.
    create = run_cli(
        repo,
        "agent",
        "feature",
        "create-feature",
        "nats-control",
        "--upstream-branch",
        "001-otel-landing",
        "--json",
    )
    assert create.returncode == 0, create.stderr

    payload = json.loads(create.stdout)
    feature_slug = payload["feature"]
    landing_branch = payload["landing_branch"]
    assert payload["upstream_branch"] == "001-otel-landing"
    assert landing_branch == feature_slug

    meta = json.loads((repo / "kitty-specs" / feature_slug / "meta.json").read_text())
    assert meta["target_branch"] == landing_branch
    assert meta["upstream_branch"] == "001-otel-landing"

    # Advance the landing branch with a marker commit so that landing and
    # upstream differ.
    assert _git(repo, "checkout", landing_branch).returncode == 0
    (repo / "landing-only.txt").write_text("landing tip\n", encoding="utf-8")
    assert _git(repo, "add", "landing-only.txt").returncode == 0
    assert _git(repo, "commit", "-m", "Advance landing branch").returncode == 0
    landing_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Return to planning/base branch and add a minimal WP01 prompt.
    assert _git(repo, "checkout", "001-otel-landing").returncode == 0
    wp_file = repo / "kitty-specs" / feature_slug / "tasks" / "WP01-setup.md"
    wp_file.write_text(
        "---\n"
        "work_package_id: WP01\n"
        "title: Setup\n"
        "lane: \"planned\"\n"
        "dependencies: []\n"
        "subtasks: [T001]\n"
        "---\n\n"
        "# Work Package Prompt: WP01 - Setup\n",
        encoding="utf-8",
    )
    assert _git(repo, "add", str(wp_file.relative_to(repo))).returncode == 0
    assert _git(repo, "commit", "-m", "Add WP01 prompt").returncode == 0

    # Run workflow implement (no --base): workspace must branch from landing.
    implement = run_cli(
        repo,
        "agent",
        "workflow",
        "implement",
        "WP01",
        "--feature",
        feature_slug,
        "--agent",
        "codex",
    )
    assert implement.returncode == 0, f"{implement.stderr}\n{implement.stdout}"

    wp_branch = f"{feature_slug}-WP01"
    is_ancestor = _git(repo, "merge-base", "--is-ancestor", landing_tip, wp_branch)
    assert is_ancestor.returncode == 0, (
        "WP workspace branch should be based on the landing branch tip"
    )
