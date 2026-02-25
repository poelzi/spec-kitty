"""Tests for implement-all slash command migration updates."""

from __future__ import annotations

from pathlib import Path

import pytest

from specify_cli.upgrade.migrations.m_0_15_4_add_implement_all_slash_command import (
    AddImplementAllSlashCommandMigration,
)


@pytest.fixture
def migration() -> AddImplementAllSlashCommandMigration:
    return AddImplementAllSlashCommandMigration()


def _write_agent_config(project_path: Path, agent_key: str = "opencode") -> None:
    kittify_dir = project_path / ".kittify"
    kittify_dir.mkdir(parents=True, exist_ok=True)
    (kittify_dir / "config.yaml").write_text(
        f"agents:\n  available:\n    - {agent_key}\n",
        encoding="utf-8",
    )


def test_detect_returns_true_when_template_content_drifted(
    tmp_path: Path, migration: AddImplementAllSlashCommandMigration
) -> None:
    """detect() should trigger when implement-all template is outdated."""
    _write_agent_config(tmp_path, "opencode")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)
    (agent_path / "spec-kitty.implement-all.md").write_text(
        "spec-kitty agent workflow schedule --json\n"
        "/spec-kitty.implement WP01\n",
        encoding="utf-8",
    )

    assert migration.detect(tmp_path) is True


def test_apply_updates_drifted_template_with_feature_flags(
    tmp_path: Path, migration: AddImplementAllSlashCommandMigration
) -> None:
    """apply() should replace drifted templates with canonical feature-aware content."""
    _write_agent_config(tmp_path, "opencode")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)
    target = agent_path / "spec-kitty.implement-all.md"
    target.write_text(
        "spec-kitty agent workflow schedule --json\n"
        "/spec-kitty.implement WP01\n",
        encoding="utf-8",
    )

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    content = target.read_text(encoding="utf-8")
    assert "spec-kitty agent workflow schedule --json --feature <feature-slug>" in content
    assert "/spec-kitty.implement <WP_ID> --feature <feature-slug>" in content
    assert "spec-kitty agent tasks status --json --feature <feature-slug>" in content


def test_detect_returns_false_when_template_is_current(
    tmp_path: Path, migration: AddImplementAllSlashCommandMigration
) -> None:
    """detect() should be false after apply writes canonical content."""
    _write_agent_config(tmp_path, "opencode")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)

    result = migration.apply(tmp_path, dry_run=False)
    assert result.success is True

    assert migration.detect(tmp_path) is False
