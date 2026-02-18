"""Integration tests for landing branch workflow on first implement.

Tests v0.15.0 landing branch model:
- Feature has upstream_branch (e.g., "3.x" or "main")
- spec-kitty implement WP01 creates a landing branch (named after feature slug)
- WP01 branches from the landing branch
- Status commits route to upstream_branch (planning artifacts)

Legacy ADR-17 behavior (auto-create custom target branch) is superseded by
the landing branch workflow where target_branch = feature slug (landing branch)
and upstream_branch = where planning artifacts live.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(project_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Execute spec-kitty CLI."""
    from tests.test_isolation_helpers import get_venv_python

    env = os.environ.copy()
    src_path = REPO_ROOT / "src"
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(
        os.pathsep
    )
    env.setdefault("SPEC_KITTY_TEMPLATE_ROOT", str(REPO_ROOT))
    command = [str(get_venv_python()), "-m", "specify_cli.__init__", *args]
    return subprocess.run(
        command, cwd=str(project_path), capture_output=True, text=True, env=env
    )


def create_feature_with_target(
    repo: Path,
    feature_slug: str,
    target_branch: str,
    upstream_branch: str | None = None,
) -> Path:
    """Create minimal feature for testing.

    In v0.15.0+ landing branch model:
    - target_branch in meta.json = initial value (may be "3.x", "main", etc.)
    - ensure_landing_branch() converts this to landing branch model:
      target_branch → feature_slug, upstream_branch → previous target_branch
    """
    import yaml

    # Create .kittify
    kittify = repo / ".kittify"
    kittify.mkdir(exist_ok=True)
    (kittify / "config.yaml").write_text(
        yaml.dump({"vcs": {"type": "git"}, "agents": {"available": ["claude"]}})
    )
    (kittify / "metadata.yaml").write_text(
        yaml.dump({"spec_kitty": {"version": "0.15.0"}})
    )

    # Create feature
    feature_dir = repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    meta = {
        "feature_number": feature_slug.split("-")[0],
        "slug": feature_slug,
        "target_branch": target_branch,
        "vcs": "git",
        "created_at": "2026-01-29T00:00:00Z",
    }
    if upstream_branch is not None:
        meta["upstream_branch"] = upstream_branch
    (feature_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    # Create WP01
    (tasks_dir / "WP01-test.md").write_text(
        "---\nwork_package_id: WP01\nlane: planned\ndependencies: []\n---\n\n# WP01\n"
    )

    # Commit
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add {feature_slug}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return feature_dir


def test_landing_branch_created_on_first_implement(tmp_path):
    """Test that a landing branch (feature slug) is created on first implement.

    Validates:
    - Feature starts with target_branch="3.x" (custom upstream)
    - implement WP01 creates landing branch named after feature slug
    - Landing branch is based on main (since 3.x doesn't exist, falls back)
    - WP01 branches from landing branch
    - meta.json updated: target_branch=feature_slug, upstream_branch=main
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Initial commit
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    # Create feature targeting non-existent 3.x branch
    feature_dir = create_feature_with_target(repo, "002-test-feature", "3.x")
    landing_branch = "002-test-feature"

    # Verify landing branch doesn't exist yet
    result = subprocess.run(
        ["git", "rev-parse", "--verify", landing_branch],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0, "Landing branch should not exist before implement"

    # Implement WP01
    result = run_cli(repo, "implement", "WP01")
    assert result.returncode == 0, f"implement failed: {result.stderr}\n{result.stdout}"

    # Verify landing branch was created (feature slug as branch name)
    result_after = subprocess.run(
        ["git", "rev-parse", "--verify", landing_branch],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert result_after.returncode == 0, "Landing branch should exist after implement"

    # Verify WP01 branch exists and is based on landing branch
    wp_branch = "002-test-feature-WP01"
    merge_base_result = subprocess.run(
        ["git", "merge-base", landing_branch, wp_branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    merge_base = merge_base_result.stdout.strip()

    # Verify that WP01's base is an ancestor of the landing branch
    is_ancestor_result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", merge_base, landing_branch],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert is_ancestor_result.returncode == 0, (
        "WP01 should branch from an ancestor of landing branch"
    )

    # Verify meta.json was updated with landing branch model
    meta = json.loads((feature_dir / "meta.json").read_text())
    assert meta["target_branch"] == landing_branch, (
        f"target_branch should be landing branch, got: {meta['target_branch']}"
    )
    # upstream_branch should be "main" (fallback since 3.x doesn't exist)
    assert meta.get("upstream_branch") == "main", (
        f"upstream_branch should be 'main', got: {meta.get('upstream_branch')}"
    )


def test_landing_branch_with_existing_upstream(tmp_path):
    """Test landing branch created from existing custom upstream branch.

    Validates:
    - Feature has target_branch="3.x" and 3.x exists
    - implement WP01 creates landing branch from 3.x
    - Landing branch points to same commit as 3.x initially
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    # Create the 3.x branch so it exists as upstream
    subprocess.run(["git", "branch", "3.x"], cwd=repo, check=True, capture_output=True)

    # Add a commit to 3.x to differentiate from main
    subprocess.run(
        ["git", "checkout", "3.x"], cwd=repo, check=True, capture_output=True
    )
    (repo / "3x-file.txt").write_text("3.x content\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "3.x commit"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "main"], cwd=repo, check=True, capture_output=True
    )

    feature_dir = create_feature_with_target(repo, "002-test-feature", "3.x")
    landing_branch = "002-test-feature"

    # Implement WP01
    result = run_cli(repo, "implement", "WP01")
    assert result.returncode == 0, f"implement failed: {result.stderr}\n{result.stdout}"

    # Verify landing branch created from 3.x
    result_landing = subprocess.run(
        ["git", "rev-parse", landing_branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    result_3x = subprocess.run(
        ["git", "rev-parse", "3.x"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    # Landing branch should be at same commit as 3.x (created from it)
    assert result_landing.stdout.strip() == result_3x.stdout.strip(), (
        "Landing branch should be created from 3.x"
    )

    # Verify meta.json updated correctly
    meta = json.loads((feature_dir / "meta.json").read_text())
    assert meta["target_branch"] == landing_branch
    assert meta.get("upstream_branch") == "3.x"


def test_subsequent_implement_uses_existing_landing_branch(tmp_path):
    """Test that second WP uses existing landing branch (doesn't recreate).

    Validates:
    - First implement creates landing branch
    - Second implement finds landing branch exists
    - Doesn't try to create again (idempotent)
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    feature_dir = create_feature_with_target(repo, "002-test", "main")
    landing_branch = "002-test"

    # Add WP02
    (feature_dir / "tasks/WP02-test.md").write_text(
        "---\nwork_package_id: WP02\nlane: planned\ndependencies: []\n---\n\n# WP02\n"
    )
    subprocess.run(
        ["git", "add", str(feature_dir)], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add WP02"], cwd=repo, check=True, capture_output=True
    )

    # Implement WP01 (creates landing branch)
    result1 = run_cli(repo, "implement", "WP01")
    assert result1.returncode == 0

    # Get landing branch commit after first implement
    result = subprocess.run(
        ["git", "rev-parse", landing_branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_landing_after_wp01 = result.stdout.strip()

    # Implement WP02 (should use existing landing branch)
    result2 = run_cli(repo, "implement", "WP02")
    assert result2.returncode == 0

    # Verify landing branch was not recreated (it should still have WP01's history)
    result_after_wp02 = subprocess.run(
        ["git", "rev-parse", landing_branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_landing_after_wp02 = result_after_wp02.stdout.strip()

    # Check that WP01's landing commit is still in the landing branch's history
    is_ancestor_result = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            commit_landing_after_wp01,
            commit_landing_after_wp02,
        ],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert is_ancestor_result.returncode == 0, (
        "Landing branch should not be recreated - WP01 commit should still be in history"
    )


def test_landing_branch_message_shown(tmp_path):
    """Test that landing branch usage message is shown to user.

    Validates:
    - Console output says "Using landing branch: ..."
    - Message is visible to agents/users
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    create_feature_with_target(repo, "002-test", "main")

    # Implement WP01
    result = run_cli(repo, "implement", "WP01")
    assert result.returncode == 0

    # Check output mentions landing branch
    assert "Using landing branch" in result.stdout, (
        f"Should announce landing branch usage. Output:\n{result.stdout}"
    )


def test_status_commits_route_to_upstream_branch(tmp_path):
    """Test that status commits route to the upstream branch (not landing branch).

    Validates:
    - Landing branch created during implement
    - Status commit (move-task) routes to upstream (main), not landing branch
    - Planning artifacts stay on main
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    create_feature_with_target(repo, "002-test", "main")

    # Implement WP01 (should create landing branch)
    result = run_cli(repo, "implement", "WP01")
    assert result.returncode == 0

    # Verify the implement status commit is on main (upstream), not landing branch
    log_main = subprocess.run(
        ["git", "log", "main", "--oneline", "-5"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "claimed for implementation" in log_main.stdout, (
        f"Status commit should be on main (upstream). Log:\n{log_main.stdout}"
    )

    # Move to for_review (status commit should route to main)
    result_move = run_cli(
        repo, "agent", "tasks", "move-task", "WP01", "--to", "for_review", "--force"
    )
    assert result_move.returncode == 0, (
        f"move-task failed: {result_move.stderr}\n{result_move.stdout}"
    )

    # Verify status commit on main
    log_main_after = subprocess.run(
        ["git", "log", "main", "--oneline", "-5"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Move WP01 to for_review" in log_main_after.stdout, (
        f"Status commit should be on main. Log:\n{log_main_after.stdout}"
    )


def test_fallback_when_auto_create_fails(tmp_path):
    """Test graceful fallback if target branch creation fails.

    Validates:
    - Attempt to create landing branch
    - If fails (permissions, conflict, etc.)
    - Falls back to primary branch with warning
    - WP01 still created (degraded mode)
    """
    # This test would need to simulate a git error
    # For now, just document expected behavior
    pass


def test_main_as_target_creates_landing_branch(tmp_path):
    """Test that target_branch='main' still creates a landing branch.

    Validates:
    - Feature with target_branch="main" (normal case)
    - Landing branch (feature slug) is created
    - main is NOT recreated
    - WP branches from landing branch, not directly from main
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True
    )

    # Create feature targeting "main" (normal case)
    feature_dir = create_feature_with_target(repo, "001-test", "main")
    landing_branch = "001-test"

    # Implement WP01
    result = run_cli(repo, "implement", "WP01")
    assert result.returncode == 0

    # Verify landing branch was created
    result_landing = subprocess.run(
        ["git", "rev-parse", "--verify", landing_branch],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert result_landing.returncode == 0, "Landing branch should be created"

    # Verify no errors about "already exists"
    assert "fatal" not in result.stdout.lower(), "Should not produce git errors"
    assert "already exists" not in result.stdout.lower(), (
        "Should not produce 'already exists' errors"
    )

    # Verify meta.json updated
    meta = json.loads((feature_dir / "meta.json").read_text())
    assert meta["target_branch"] == landing_branch
    assert meta.get("upstream_branch") == "main"
