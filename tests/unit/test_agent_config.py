"""Agent config parsing and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from specify_cli.core.agent_config import (
    AgentConfig,
    AgentConfigError,
    AgentRolePreference,
    AgentSelectionConfig,
    load_agent_config,
    save_agent_config,
)


def _write_config(tmp_path: Path, content: str) -> Path:
    kittify = tmp_path / ".kittify"
    kittify.mkdir(parents=True, exist_ok=True)
    config_file = kittify / "config.yaml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


class TestCorruptYaml:
    def test_corrupt_yaml_clear_error(self, tmp_path: Path) -> None:
        """Corrupt YAML should produce parse error, not silent fallback."""
        _write_config(tmp_path, "invalid: yaml: content: [")

        with pytest.raises(AgentConfigError) as exc_info:
            load_agent_config(tmp_path)

        assert "Invalid YAML" in str(exc_info.value)
        assert "config.yaml" in str(exc_info.value)


class TestUnknownAgentKey:
    def test_unknown_agent_reported(self, tmp_path: Path) -> None:
        """Unknown agent key should be explicitly reported."""
        _write_config(tmp_path, "agents:\n  available:\n    - unknown_agent_xyz\n")

        with pytest.raises(AgentConfigError) as exc_info:
            load_agent_config(tmp_path)

        message = str(exc_info.value)
        assert "unknown_agent_xyz" in message
        assert "Valid agents" in message


class TestRolePreferenceRemoval:
    def test_save_agent_config_only_persists_available_agents(self, tmp_path: Path) -> None:
        """Persisted agent config should only include agents.available."""
        config = AgentConfig(available=["claude", "codex"])

        save_agent_config(tmp_path, config)
        content = (tmp_path / ".kittify" / "config.yaml").read_text(encoding="utf-8")

        assert "strategy:" not in content
        assert "selection:" not in content
        assert "available:" in content


class TestRolePreferenceSupport:
    def test_load_parses_tool_and_model_preferences(self, tmp_path: Path) -> None:
        """Role preferences support same tool with different models."""
        _write_config(
            tmp_path,
            "agents:\n"
            "  available:\n"
            "    - opencode\n"
            "  selection:\n"
            "    preferred_implementer:\n"
            "      tool: opencode\n"
            "      model: gpt-5-coder\n"
            "    preferred_reviewer: opencode@gpt-5-review\n",
        )

        config = load_agent_config(tmp_path)

        assert config.selection is not None
        assert config.selection.preferred_implementer is not None
        assert config.selection.preferred_implementer.tool == "opencode"
        assert config.selection.preferred_implementer.model == "gpt-5-coder"
        assert config.selection.preferred_reviewer is not None
        assert config.selection.preferred_reviewer.tool == "opencode"
        assert config.selection.preferred_reviewer.model == "gpt-5-review"

    def test_load_accepts_legacy_role_keys(self, tmp_path: Path) -> None:
        """Legacy implementer_agent/reviewer_agent keys still load."""
        _write_config(
            tmp_path,
            "agents:\n"
            "  available:\n"
            "    - claude\n"
            "    - codex\n"
            "  selection:\n"
            "    strategy: preferred\n"
            "    implementer_agent: claude\n"
            "    reviewer_agent: codex\n",
        )

        config = load_agent_config(tmp_path)

        assert config.selection is not None
        assert config.selection.preferred_implementer is not None
        assert config.selection.preferred_implementer.tool == "claude"
        assert config.selection.preferred_reviewer is not None
        assert config.selection.preferred_reviewer.tool == "codex"

    def test_save_writes_model_preferences_and_drops_strategy(self, tmp_path: Path) -> None:
        """Saving keeps model hints and omits deprecated strategy."""
        _write_config(
            tmp_path,
            "agents:\n"
            "  available:\n"
            "    - opencode\n"
            "  selection:\n"
            "    strategy: preferred\n"
            "    preferred_implementer: opencode\n",
        )

        config = AgentConfig(
            available=["opencode"],
            selection=AgentSelectionConfig(
                preferred_implementer=AgentRolePreference(
                    tool="opencode",
                    model="gpt-5-coder",
                ),
                preferred_reviewer=AgentRolePreference(
                    tool="opencode",
                    model="gpt-5-review",
                ),
            ),
        )

        save_agent_config(tmp_path, config)
        content = (tmp_path / ".kittify" / "config.yaml").read_text(encoding="utf-8")

        assert "strategy:" not in content
        assert "selection:" in content
        assert "preferred_implementer:" in content
        assert "preferred_reviewer:" in content
        assert "tool: opencode" in content
        assert "model: gpt-5-coder" in content
        assert "model: gpt-5-review" in content

    def test_invalid_role_agent_key_is_reported(self, tmp_path: Path) -> None:
        """Unknown role preference agents are rejected clearly."""
        _write_config(
            tmp_path,
            "agents:\n"
            "  available:\n"
            "    - opencode\n"
            "  selection:\n"
            "    preferred_reviewer: not-a-real-agent\n",
        )

        with pytest.raises(AgentConfigError) as exc_info:
            load_agent_config(tmp_path)

        message = str(exc_info.value)
        assert "agents.selection.preferred_reviewer" in message
        assert "not-a-real-agent" in message
