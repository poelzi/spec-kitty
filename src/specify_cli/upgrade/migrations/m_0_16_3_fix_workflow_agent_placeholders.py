"""Migration: Replace workflow --agent placeholders with concrete agent names.

Some generated slash command files contained the literal placeholder
`<your-name>` in workflow command examples:

    spec-kitty agent workflow implement ... --agent <your-name>

When agents executed these commands literally, shells interpreted `<...>` as
redirection syntax, causing command failures before workspace creation.

This migration patches existing generated command files so each configured
agent gets its concrete name in `--agent` flags.
"""

from __future__ import annotations

from pathlib import Path

from specify_cli.agent_utils.directories import (
    AGENT_DIR_TO_KEY,
    get_agent_dirs_for_project,
)
from specify_cli.core.config import AGENT_COMMAND_CONFIG

from ..registry import MigrationRegistry
from .base import BaseMigration, MigrationResult


@MigrationRegistry.register
class FixWorkflowAgentPlaceholdersMigration(BaseMigration):
    """Replace `<your-name>` placeholders in implement/review command files."""

    migration_id = "0.16.3_fix_workflow_agent_placeholders"
    description = "Replace workflow --agent placeholders with concrete agent names"
    target_version = "0.16.3"

    PLACEHOLDER = "<your-name>"

    def _target_files(self, project_path: Path) -> list[tuple[Path, str]]:
        """Return command files that should contain agent-specific workflow commands.

        Returns tuples of (file_path, agent_name).
        """
        targets: list[tuple[Path, str]] = []

        for agent_root, subdir in get_agent_dirs_for_project(project_path):
            agent_key = AGENT_DIR_TO_KEY.get(agent_root)
            if not agent_key:
                continue

            config = AGENT_COMMAND_CONFIG.get(agent_key)
            if not config:
                continue

            agent_dir = project_path / agent_root / subdir
            if not agent_dir.exists():
                continue

            ext = config.get("ext", "md")
            for stem in ("implement", "review"):
                filename = f"spec-kitty.{stem}.{ext}" if ext else f"spec-kitty.{stem}"
                file_path = agent_dir / filename
                if file_path.exists():
                    targets.append((file_path, agent_key))

        return targets

    def detect(self, project_path: Path) -> bool:
        """Detect if any generated workflow command file still uses placeholders."""
        for file_path, _agent_name in self._target_files(project_path):
            try:
                content = file_path.read_text(encoding="utf-8")
            except OSError:
                continue

            if self.PLACEHOLDER in content:
                return True

        return False

    def can_apply(self, project_path: Path) -> tuple[bool, str]:
        """Ensure this looks like a spec-kitty project."""
        if not (project_path / ".kittify").exists():
            return False, "No .kittify directory (not a spec-kitty project)"
        return True, ""

    def apply(self, project_path: Path, dry_run: bool = False) -> MigrationResult:
        """Replace placeholders in generated implement/review command files."""
        changes: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        updated_count = 0
        for file_path, agent_name in self._target_files(project_path):
            try:
                content = file_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"Failed reading {file_path}: {exc}")
                continue

            if self.PLACEHOLDER not in content:
                continue

            updated = content.replace(self.PLACEHOLDER, agent_name)
            if dry_run:
                changes.append(f"Would update {file_path.relative_to(project_path)}")
                updated_count += 1
                continue

            try:
                file_path.write_text(updated, encoding="utf-8")
                changes.append(f"Updated {file_path.relative_to(project_path)}")
                updated_count += 1
            except OSError as exc:
                errors.append(f"Failed writing {file_path}: {exc}")

        if updated_count == 0 and not errors:
            warnings.append("No workflow placeholders required updates")

        return MigrationResult(
            success=len(errors) == 0,
            changes_made=changes,
            errors=errors,
            warnings=warnings,
        )
