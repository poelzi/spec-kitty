"""Canonical agent configuration helpers.

This module stores and loads agent configuration from `.kittify/config.yaml`.
It currently supports:

- `agents.available`
- Optional role preferences under `agents.selection` for implementation/review,
  including model hints (for example using the same tool with different models).

Legacy orchestration strategy fields are accepted on read and dropped on write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from specify_cli.core.config import AI_CHOICES

import logging

logger = logging.getLogger(__name__)


class AgentConfigError(RuntimeError):
    """Raised when .kittify/config.yaml cannot be parsed or validated."""


@dataclass
class AgentConfig:
    """Full agent configuration.

    Attributes:
        available: List of agent IDs that are available for use.
        selection: Optional role preferences for implementation/review.
    """

    available: list[str] = field(default_factory=list)
    selection: "AgentSelectionConfig | None" = None


@dataclass
class AgentRolePreference:
    """Preferred agent role assignment with optional model hint.

    Attributes:
        tool: Agent key (must be present in ``AI_CHOICES``).
        model: Optional model identifier for the selected tool.
    """

    tool: str
    model: str | None = None


@dataclass
class AgentSelectionConfig:
    """Preferred agent assignments for implementation/review lanes."""

    preferred_implementer: AgentRolePreference | None = None
    preferred_reviewer: AgentRolePreference | None = None


def _validate_agent_key(agent_key: str, *, context: str) -> None:
    """Validate a configured agent key against known choices."""
    if agent_key not in AI_CHOICES:
        valid_agents = ", ".join(sorted(AI_CHOICES.keys()))
        raise AgentConfigError(
            f"Unknown agent key in {context}: {agent_key}. "
            f"Valid agents: {valid_agents}"
        )


def _parse_role_preference(
    raw_value: object,
    *,
    field_name: str,
) -> AgentRolePreference | None:
    """Parse a role preference value from YAML data.

    Supported forms:

    - String: ``opencode`` or ``opencode@gpt-5``
    - Mapping: ``{tool: opencode, model: gpt-5}``
    - Mapping (legacy key): ``{agent: opencode, model: gpt-5}``
    """
    if raw_value is None:
        return None

    tool: str
    model: str | None = None

    if isinstance(raw_value, str):
        token = raw_value.strip()
        if not token:
            return None

        if "@" in token:
            parsed_tool, parsed_model = token.split("@", 1)
            parsed_tool = parsed_tool.strip()
            parsed_model = parsed_model.strip()
            if not parsed_tool or not parsed_model:
                raise AgentConfigError(
                    f"Invalid agents.selection.{field_name}: "
                    "expected '<agent>' or '<agent>@<model>'"
                )
            tool = parsed_tool
            model = parsed_model
        else:
            tool = token
    elif isinstance(raw_value, dict):
        tool_value = raw_value.get("tool", raw_value.get("agent"))
        if not isinstance(tool_value, str) or not tool_value.strip():
            raise AgentConfigError(
                f"Invalid agents.selection.{field_name}: "
                "mapping requires non-empty 'tool' (or legacy 'agent')"
            )

        tool = tool_value.strip()

        model_value = raw_value.get("model")
        if model_value is not None:
            if not isinstance(model_value, str):
                raise AgentConfigError(
                    f"Invalid agents.selection.{field_name}.model: expected a string"
                )
            model = model_value.strip() or None
    else:
        raise AgentConfigError(
            f"Invalid agents.selection.{field_name}: expected string or mapping"
        )

    _validate_agent_key(tool, context=f"agents.selection.{field_name}")
    return AgentRolePreference(tool=tool, model=model)


def _parse_selection_config(agents_data: dict[str, object]) -> AgentSelectionConfig | None:
    """Parse optional role-selection settings from the agents block."""
    selection_data = agents_data.get("selection")
    if selection_data is None:
        return None

    if not isinstance(selection_data, dict):
        raise AgentConfigError("Invalid agents.selection in config.yaml: expected a mapping")

    implementer_raw = selection_data.get("preferred_implementer")
    if implementer_raw is None:
        implementer_raw = selection_data.get("implementer_agent")

    reviewer_raw = selection_data.get("preferred_reviewer")
    if reviewer_raw is None:
        reviewer_raw = selection_data.get("reviewer_agent")

    preferred_implementer = _parse_role_preference(
        implementer_raw,
        field_name="preferred_implementer",
    )
    preferred_reviewer = _parse_role_preference(
        reviewer_raw,
        field_name="preferred_reviewer",
    )

    if preferred_implementer is None and preferred_reviewer is None:
        return None

    return AgentSelectionConfig(
        preferred_implementer=preferred_implementer,
        preferred_reviewer=preferred_reviewer,
    )


def _serialize_role_preference(preference: AgentRolePreference) -> str | dict[str, str]:
    """Serialize role preference for YAML output.

    - Tool-only preferences stay as plain strings for readability/back-compat.
    - Tool+model preferences are written as a mapping.
    """
    if preference.model:
        return {
            "tool": preference.tool,
            "model": preference.model,
        }
    return preference.tool


def _serialize_selection_config(selection: AgentSelectionConfig | None) -> dict[str, object] | None:
    """Serialize role-selection settings, omitting empty fields."""
    if selection is None:
        return None

    payload: dict[str, object] = {}
    if selection.preferred_implementer is not None:
        payload["preferred_implementer"] = _serialize_role_preference(
            selection.preferred_implementer
        )
    if selection.preferred_reviewer is not None:
        payload["preferred_reviewer"] = _serialize_role_preference(
            selection.preferred_reviewer
        )

    return payload or None


def load_agent_config(repo_root: Path) -> AgentConfig:
    """Load agent configuration from .kittify/config.yaml."""
    config_file = repo_root / ".kittify" / "config.yaml"

    if not config_file.exists():
        logger.warning("Config file not found: %s", config_file)
        return AgentConfig()

    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        raise AgentConfigError(f"Invalid YAML in {config_file}: {exc}") from exc

    agents_data = data.get("agents", {})
    if not agents_data:
        logger.info("No agents section in config.yaml")
        return AgentConfig()

    available = agents_data.get("available", [])
    if isinstance(available, str):
        available = [available]
    if not isinstance(available, list):
        raise AgentConfigError(
            "Invalid agents.available in config.yaml: expected a list of agent keys"
        )

    invalid_agents = [agent for agent in available if agent not in AI_CHOICES]
    if invalid_agents:
        valid_agents = ", ".join(sorted(AI_CHOICES.keys()))
        unknown = ", ".join(sorted(invalid_agents))
        raise AgentConfigError(
            f"Unknown agent key(s) in config.yaml: {unknown}. "
            f"Valid agents: {valid_agents}"
        )

    selection = _parse_selection_config(agents_data)

    return AgentConfig(available=available, selection=selection)


def save_agent_config(repo_root: Path, config: AgentConfig) -> None:
    """Save agent configuration to .kittify/config.yaml.

    Merges with existing config and preserves unrelated sections.
    """
    config_dir = repo_root / ".kittify"
    config_file = config_dir / "config.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}
        config_dir.mkdir(parents=True, exist_ok=True)

    serialized_selection = _serialize_selection_config(config.selection)

    agents_block: dict[str, object] = {
        "available": config.available,
    }
    if serialized_selection:
        agents_block["selection"] = serialized_selection

    data["agents"] = agents_block

    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    logger.info("Saved agent config to %s", config_file)


def get_configured_agents(repo_root: Path) -> list[str]:
    """Return configured agents (possibly empty)."""
    return load_agent_config(repo_root).available


__all__ = [
    "AgentConfig",
    "AgentSelectionConfig",
    "AgentRolePreference",
    "AgentConfigError",
    "load_agent_config",
    "save_agent_config",
    "get_configured_agents",
]
