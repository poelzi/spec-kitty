"""Tests for change+integrate slash command migration (m_0_15_0_add_change_slash_command)."""

import pytest

from specify_cli.upgrade.migrations.m_0_15_0_add_change_slash_command import (
    AddChangeSlashCommandMigration,
)


@pytest.fixture
def migration():
    return AddChangeSlashCommandMigration()


ALL_AGENTS = [
    ("claude", ".claude", "commands"),
    ("copilot", ".github", "prompts"),
    ("gemini", ".gemini", "commands"),
    ("cursor", ".cursor", "commands"),
    ("qwen", ".qwen", "commands"),
    ("opencode", ".opencode", "command"),
    ("windsurf", ".windsurf", "workflows"),
    ("codex", ".codex", "prompts"),
    ("kilocode", ".kilocode", "workflows"),
    ("auggie", ".augment", "commands"),
    ("roo", ".roo", "commands"),
    ("q", ".amazonq", "prompts"),
]


@pytest.mark.parametrize("agent_key,agent_dir,subdir", ALL_AGENTS)
def test_templates_deployed_for_agent(
    tmp_path, migration, agent_key, agent_dir, subdir
):
    """Verify spec-kitty.change.md and spec-kitty.integrate.md are created for each agent."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text(
        f"agents:\n  available:\n    - {agent_key}\n", encoding="utf-8"
    )

    agent_path = tmp_path / agent_dir / subdir
    agent_path.mkdir(parents=True)

    assert migration.detect(tmp_path) is True

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    assert len(result.errors) == 0

    # Verify change template
    change_dest = agent_path / "spec-kitty.change.md"
    assert change_dest.exists()
    change_content = change_dest.read_text(encoding="utf-8")
    assert (
        "spec-kitty.change" in change_content or "Mid-Stream Change" in change_content
    )

    # Verify integrate template
    integrate_dest = agent_path / "spec-kitty.integrate.md"
    assert integrate_dest.exists()
    integrate_content = integrate_dest.read_text(encoding="utf-8")
    assert "integrate" in integrate_content.lower()


def test_detect_returns_false_when_already_present(tmp_path, migration):
    """detect() returns False when all templates exist in all configured agents."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)
    (agent_path / "spec-kitty.change.md").write_text("placeholder", encoding="utf-8")
    (agent_path / "spec-kitty.integrate.md").write_text("placeholder", encoding="utf-8")

    assert migration.detect(tmp_path) is False


def test_detect_returns_true_when_integrate_missing(tmp_path, migration):
    """detect() returns True when only change template exists (integrate missing)."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)
    (agent_path / "spec-kitty.change.md").write_text("placeholder", encoding="utf-8")

    assert migration.detect(tmp_path) is True


def test_respects_agent_config(tmp_path, migration):
    """Only configured agents are updated; orphaned agents are skipped."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    # Configured agent
    opencode_path = tmp_path / ".opencode" / "command"
    opencode_path.mkdir(parents=True)

    # Orphaned agent (not in config)
    claude_path = tmp_path / ".claude" / "commands"
    claude_path.mkdir(parents=True)

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    assert (opencode_path / "spec-kitty.change.md").exists()
    assert (opencode_path / "spec-kitty.integrate.md").exists()
    assert not (claude_path / "spec-kitty.change.md").exists()
    assert not (claude_path / "spec-kitty.integrate.md").exists()


def test_handles_missing_directories(tmp_path, migration):
    """Gracefully skips agents whose directories don't exist."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    # Don't create the agent directory

    result = migration.apply(tmp_path, dry_run=False)

    assert result.success is True
    assert len(result.errors) == 0


def test_dry_run_does_not_write(tmp_path, migration):
    """Dry-run reports changes without writing files."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)

    result = migration.apply(tmp_path, dry_run=True)

    assert result.success is True
    assert any("Would create" in c for c in result.changes_made)
    assert not (agent_path / "spec-kitty.change.md").exists()


def test_idempotent_when_content_matches(tmp_path, migration):
    """Skip copy when destination already has identical content."""
    kittify_dir = tmp_path / ".kittify"
    kittify_dir.mkdir()

    config_file = kittify_dir / "config.yaml"
    config_file.write_text("agents:\n  available:\n    - opencode\n", encoding="utf-8")

    agent_path = tmp_path / ".opencode" / "command"
    agent_path.mkdir(parents=True)

    # Pre-populate with correct content by running apply once
    result1 = migration.apply(tmp_path, dry_run=False)
    assert result1.success is True
    assert len(result1.changes_made) > 0

    # Second apply should produce no changes (idempotent)
    result2 = migration.apply(tmp_path, dry_run=False)
    assert result2.success is True
    assert len(result2.changes_made) == 0
