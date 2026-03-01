from __future__ import annotations

from pathlib import Path

import pytest

from specify_cli.upgrade.migrations.m_0_16_3_fix_workflow_agent_placeholders import (
    FixWorkflowAgentPlaceholdersMigration,
)


@pytest.fixture
def migration() -> FixWorkflowAgentPlaceholdersMigration:
    return FixWorkflowAgentPlaceholdersMigration()


def _write_agent_config(project_path: Path, agent_key: str) -> None:
    kittify_dir = project_path / ".kittify"
    kittify_dir.mkdir(parents=True, exist_ok=True)
    (kittify_dir / "config.yaml").write_text(
        f"agents:\n  available:\n    - {agent_key}\n",
        encoding="utf-8",
    )


def test_detects_placeholder_in_markdown_prompt(
    tmp_path: Path, migration: FixWorkflowAgentPlaceholdersMigration
) -> None:
    _write_agent_config(tmp_path, "opencode")

    prompt = tmp_path / ".opencode" / "command" / "spec-kitty.implement.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(
        "spec-kitty agent workflow implement $ARGUMENTS --agent <your-name>\n",
        encoding="utf-8",
    )

    assert migration.detect(tmp_path) is True


def test_apply_replaces_placeholder_in_agent_prompts(
    tmp_path: Path, migration: FixWorkflowAgentPlaceholdersMigration
) -> None:
    _write_agent_config(tmp_path, "opencode")

    implement_prompt = tmp_path / ".opencode" / "command" / "spec-kitty.implement.md"
    review_prompt = tmp_path / ".opencode" / "command" / "spec-kitty.review.md"
    implement_prompt.parent.mkdir(parents=True, exist_ok=True)

    implement_prompt.write_text(
        "spec-kitty agent workflow implement $ARGUMENTS --agent <your-name>\n",
        encoding="utf-8",
    )
    review_prompt.write_text(
        "spec-kitty agent workflow review $ARGUMENTS --agent <your-name>\n",
        encoding="utf-8",
    )

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    assert "--agent opencode" in implement_prompt.read_text(encoding="utf-8")
    assert "--agent opencode" in review_prompt.read_text(encoding="utf-8")
    assert "<your-name>" not in implement_prompt.read_text(encoding="utf-8")
    assert "<your-name>" not in review_prompt.read_text(encoding="utf-8")


def test_apply_replaces_placeholder_in_toml_prompt(
    tmp_path: Path, migration: FixWorkflowAgentPlaceholdersMigration
) -> None:
    _write_agent_config(tmp_path, "gemini")

    prompt = tmp_path / ".gemini" / "commands" / "spec-kitty.implement.toml"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(
        "prompt = '''\nspec-kitty agent workflow implement {{args}} --agent <your-name>\n'''\n",
        encoding="utf-8",
    )

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    content = prompt.read_text(encoding="utf-8")
    assert "--agent gemini" in content
    assert "<your-name>" not in content


def test_detect_false_when_no_placeholder(
    tmp_path: Path, migration: FixWorkflowAgentPlaceholdersMigration
) -> None:
    _write_agent_config(tmp_path, "opencode")

    prompt = tmp_path / ".opencode" / "command" / "spec-kitty.implement.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(
        "spec-kitty agent workflow implement $ARGUMENTS --agent opencode\n",
        encoding="utf-8",
    )

    assert migration.detect(tmp_path) is False
