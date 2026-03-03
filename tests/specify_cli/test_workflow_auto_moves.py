"""Tests for workflow auto lane transitions."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands.agent import workflow
from specify_cli.frontmatter import write_frontmatter
from specify_cli.tasks_support import build_document, extract_scalar, set_scalar, split_frontmatter


def write_tasks_md(feature_dir: Path, wp_id: str, subtasks: list[str], done: bool = True) -> None:
    """Write a minimal tasks.md with checkbox status for a WP."""
    checkbox = "[x]" if done else "[ ]"
    lines = [f"## {wp_id} Test", ""]
    for task_id in subtasks:
        lines.append(f"- {checkbox} {task_id} Placeholder task")
    (feature_dir / "tasks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_wp_file(path: Path, wp_id: str, lane: str, review_status: str = "") -> None:
    """Create a minimal WP prompt file."""
    frontmatter = {
        "work_package_id": wp_id,
        "subtasks": ["T001"],
        "title": f"{wp_id} Test",
        "phase": "Phase 0",
        "lane": lane,
        "assignee": "",
        "agent": "",
        "shell_pid": "",
        "review_status": review_status,
        "reviewed_by": "",
        "dependencies": [],
        "history": [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "lane": lane,
                "agent": "system",
                "shell_pid": "",
                "action": "Prompt created",
            }
        ],
    }
    body = f"# {wp_id} Prompt\n\n## Activity Log\n- 2026-01-01T00:00:00Z – system – lane={lane} – Prompt created.\n"
    write_frontmatter(path, frontmatter, body)


@pytest.fixture()
def workflow_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal repo root for workflow tests."""
    repo_root = tmp_path
    (repo_root / ".kittify").mkdir()
    monkeypatch.setenv("SPECIFY_REPO_ROOT", str(repo_root))
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        "specify_cli.cli.commands.agent.workflow._ensure_target_branch_checked_out",
        lambda repo_root, feature_slug: (repo_root, "main"),
    )
    return repo_root


def test_workflow_implement_auto_moves_to_doing(workflow_repo: Path) -> None:
    """Implement workflow should move planned -> doing (for_review is manual after completion)."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="planned")

    runner = CliRunner()
    # --agent is required for tracking who is implementing
    result = runner.invoke(workflow.app, ["implement", "WP01", "--feature", feature_slug, "--agent", "test-agent"])
    assert result.exit_code == 0

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, _, _ = split_frontmatter(content)
    # Implement moves to "doing", not "for_review" (that's a manual completion step)
    assert extract_scalar(frontmatter, "lane") == "doing"


def test_workflow_review_auto_moves_to_doing(workflow_repo: Path) -> None:
    """Review workflow should move for_review -> doing (done/planned is manual after review)."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="for_review")

    runner = CliRunner()
    # --agent is required for tracking who is reviewing
    result = runner.invoke(workflow.app, ["review", "WP01", "--feature", feature_slug, "--agent", "test-reviewer"])
    assert result.exit_code == 0

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, _, _ = split_frontmatter(content)
    # Review moves to "doing" to mark reviewer is working - done/planned is manual
    assert extract_scalar(frontmatter, "lane") == "doing"


def test_workflow_review_with_feedback_still_moves_to_doing(workflow_repo: Path) -> None:
    """Review workflow moves to doing even when feedback exists (reviewer makes decision)."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="for_review", review_status="has_feedback")

    runner = CliRunner()
    # --agent is required for tracking who is reviewing
    result = runner.invoke(workflow.app, ["review", "WP01", "--feature", feature_slug, "--agent", "test-reviewer"])
    assert result.exit_code == 0

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, _, _ = split_frontmatter(content)
    # Review moves to "doing" - reviewer decides to move to done or planned after
    assert extract_scalar(frontmatter, "lane") == "doing"


def test_workflow_review_tracks_reviewer_agent(workflow_repo: Path) -> None:
    """Review workflow should track the reviewer agent name."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="for_review")

    runner = CliRunner()
    result = runner.invoke(workflow.app, ["review", "WP01", "--feature", feature_slug, "--agent", "claude"])
    assert result.exit_code == 0

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, _, _ = split_frontmatter(content)
    assert extract_scalar(frontmatter, "agent") == "claude"


def test_workflow_implement_refreshes_claim_when_already_doing(workflow_repo: Path) -> None:
    """Implement workflow should refresh agent metadata even when lane is already doing."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="doing")

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, body, padding = split_frontmatter(content)
    frontmatter = set_scalar(frontmatter, "agent", "old-agent")
    frontmatter = set_scalar(frontmatter, "shell_pid", "11111")
    wp_path.write_text(build_document(frontmatter, body, padding), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        workflow.app,
        ["implement", "WP01", "--feature", feature_slug, "--agent", "new-agent"],
    )
    assert result.exit_code == 0

    updated = wp_path.read_text(encoding="utf-8")
    updated_front, updated_body, _ = split_frontmatter(updated)
    assert extract_scalar(updated_front, "lane") == "doing"
    assert extract_scalar(updated_front, "agent") == "new-agent"
    assert extract_scalar(updated_front, "shell_pid") != "11111"
    assert "Refreshed implementation claim via workflow command" in updated_body


def test_workflow_review_refreshes_claim_when_already_doing(workflow_repo: Path) -> None:
    """Review workflow should refresh agent metadata even when lane is already doing."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="doing")

    content = wp_path.read_text(encoding="utf-8")
    frontmatter, body, padding = split_frontmatter(content)
    frontmatter = set_scalar(frontmatter, "agent", "old-reviewer")
    frontmatter = set_scalar(frontmatter, "shell_pid", "22222")
    wp_path.write_text(build_document(frontmatter, body, padding), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        workflow.app,
        ["review", "WP01", "--feature", feature_slug, "--agent", "new-reviewer"],
    )
    assert result.exit_code == 0

    updated = wp_path.read_text(encoding="utf-8")
    updated_front, updated_body, _ = split_frontmatter(updated)
    assert extract_scalar(updated_front, "lane") == "doing"
    assert extract_scalar(updated_front, "agent") == "new-reviewer"
    assert extract_scalar(updated_front, "shell_pid") != "22222"
    assert "Refreshed review claim via workflow command" in updated_body


def test_workflow_review_defaults_to_landing_merge_target(workflow_repo: Path) -> None:
    """Review workflow should default approval merge target to landing branch."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="for_review")

    # Ensure feature metadata defines distinct landing/upstream branches
    (feature_dir / "meta.json").write_text(
        '{"target_branch": "001-test-feature", "upstream_branch": "main"}\n',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        workflow.app,
        ["review", "WP01", "--feature", feature_slug, "--agent", "claude"],
    )
    assert result.exit_code == 0

    prompt_file = Path(tempfile.gettempdir()) / "spec-kitty-review-WP01.md"
    prompt_content = prompt_file.read_text(encoding="utf-8")

    assert "Merge target mode: landing (branch: 001-test-feature)" in prompt_content


def test_workflow_review_allows_upstream_merge_target(workflow_repo: Path) -> None:
    """Review workflow should switch approval merge target to upstream when requested."""
    feature_slug = "001-test-feature"
    feature_dir = workflow_repo / "kitty-specs" / feature_slug
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    write_tasks_md(feature_dir, "WP01", ["T001"], done=True)
    wp_path = tasks_dir / "WP01-test.md"
    write_wp_file(wp_path, "WP01", lane="for_review")

    (feature_dir / "meta.json").write_text(
        '{"target_branch": "001-test-feature", "upstream_branch": "main"}\n',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        workflow.app,
        [
            "review",
            "WP01",
            "--feature",
            feature_slug,
            "--agent",
            "claude",
            "--merge-target",
            "upstream",
        ],
    )
    assert result.exit_code == 0

    prompt_file = Path(tempfile.gettempdir()) / "spec-kitty-review-WP01.md"
    prompt_content = prompt_file.read_text(encoding="utf-8")

    assert "Merge target mode: upstream (branch: main)" in prompt_content


def test_workflow_find_feature_slug_disables_latest_incomplete_fallback(
    workflow_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workflow feature detection should not auto-fallback to latest incomplete feature."""
    captured: dict[str, object] = {}

    def fake_detect_feature_slug(repo_root: Path, **kwargs):
        captured.update(kwargs)
        return "018-deterministic-workflow-runner-mvp"

    monkeypatch.setattr(
        "specify_cli.cli.commands.agent.workflow.detect_feature_slug",
        fake_detect_feature_slug,
    )

    slug = workflow._find_feature_slug(explicit_feature="018")

    assert slug == "018-deterministic-workflow-runner-mvp"
    assert captured["explicit_feature"] == "018"
    assert captured["allow_latest_incomplete_fallback"] is False
