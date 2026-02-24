"""Migration: Add spec-kitty.implement-all slash command.

Deploys the /spec-kitty.implement-all command template from
missions/software-dev/command-templates/implement-all.md to all
configured agent directories, rendered with the correct format
(Markdown or TOML) and naming conventions per agent.
"""

from __future__ import annotations

from pathlib import Path

from ..registry import MigrationRegistry
from .base import BaseMigration, MigrationResult
from specify_cli.agent_utils.directories import (
    get_agent_dirs_for_project,
    AGENT_DIR_TO_KEY,
)
from specify_cli.core.config import AGENT_COMMAND_CONFIG
from specify_cli.template.asset_generator import render_command_template


@MigrationRegistry.register
class AddImplementAllSlashCommandMigration(BaseMigration):
    """Deploy spec-kitty.implement-all to all configured agents."""

    migration_id = "0.15.4_add_implement_all_slash_command"
    description = "Add /spec-kitty.implement-all slash command to agent directories"
    target_version = "0.15.4"

    SOURCE_FILENAME = "implement-all.md"
    SOURCE_SEARCH_PATHS = [("missions", "software-dev", "command-templates")]

    def _dest_filename(self, agent_key: str) -> str:
        """Compute the destination filename for a given agent."""
        config = AGENT_COMMAND_CONFIG.get(agent_key, {})
        ext = config.get("ext", "md")
        stem = "implement-all"
        if agent_key == "codex":
            stem = stem.replace("-", "_")
        return f"spec-kitty.{stem}.{ext}" if ext else f"spec-kitty.{stem}"

    def detect(self, project_path: Path) -> bool:
        """Return True if template is missing from any configured agent."""
        agent_dirs = get_agent_dirs_for_project(project_path)

        for agent_root, subdir in agent_dirs:
            agent_dir = project_path / agent_root / subdir
            if not agent_dir.exists():
                continue
            agent_key = AGENT_DIR_TO_KEY.get(agent_root)
            if not agent_key:
                continue
            dest_name = self._dest_filename(agent_key)
            if not (agent_dir / dest_name).exists():
                return True

        return False

    def can_apply(self, project_path: Path) -> tuple[bool, str]:
        """Verify source template is available."""
        template = self._find_package_template()
        if template is None:
            return (
                False,
                f"Could not locate package {self.SOURCE_FILENAME} template. "
                "Run 'spec-kitty upgrade' again after installation.",
            )
        return True, ""

    def apply(self, project_path: Path, dry_run: bool = False) -> MigrationResult:
        """Render and deploy template to all configured agent directories."""
        changes: list[str] = []
        errors: list[str] = []

        package_template = self._find_package_template()
        if package_template is None:
            return MigrationResult(
                success=False,
                errors=[f"Could not locate package {self.SOURCE_FILENAME} template"],
            )

        agent_dirs = get_agent_dirs_for_project(project_path)

        if not agent_dirs:
            return MigrationResult(
                success=True,
                changes_made=["No agents configured, skipping"],
            )

        for agent_root, subdir in agent_dirs:
            agent_dir = project_path / agent_root / subdir
            if not agent_dir.exists():
                continue

            agent_key = AGENT_DIR_TO_KEY.get(agent_root)
            if not agent_key:
                continue

            config = AGENT_COMMAND_CONFIG.get(agent_key)
            if not config:
                continue

            dest_name = self._dest_filename(agent_key)
            dest = agent_dir / dest_name

            # Render the template through the same pipeline as init
            try:
                rendered = render_command_template(
                    package_template,
                    "bash",  # script_type (not used in this template)
                    agent_key,
                    config["arg_format"],
                    config["ext"],
                )
            except Exception as e:
                errors.append(
                    f"Failed to render for {agent_key}: {e}"
                )
                continue

            # Skip if already exists with identical content
            if dest.exists():
                try:
                    if dest.read_text(encoding="utf-8") == rendered:
                        continue
                except OSError:
                    pass

            if dry_run:
                action = "Would update" if dest.exists() else "Would create"
                changes.append(f"{action} {agent_root}/{subdir}/{dest_name}")
            else:
                try:
                    dest.write_text(rendered, encoding="utf-8")
                    action = "Updated" if dest.exists() else "Created"
                    changes.append(f"{action} {agent_root}/{subdir}/{dest_name}")
                except OSError as e:
                    errors.append(
                        f"Failed to write {agent_root}/{subdir}/{dest_name}: {e}"
                    )

        return MigrationResult(
            success=len(errors) == 0,
            changes_made=changes,
            errors=errors,
        )

    def _find_package_template(self) -> Path | None:
        """Locate the implement-all.md template in the installed package or local repo."""
        for path_parts in self.SOURCE_SEARCH_PATHS:
            found = self._search_template(path_parts)
            if found:
                return found
        return None

    def _search_template(self, path_parts: tuple[str, ...]) -> Path | None:
        """Search for template in a specific package-relative path."""
        # Try importlib.resources
        try:
            from importlib.resources import files

            pkg_files = files("specify_cli")
            template_path = pkg_files.joinpath(*path_parts, self.SOURCE_FILENAME)
            resolved = Path(str(template_path))
            if resolved.exists():
                return resolved
        except (ImportError, TypeError, AttributeError):
            pass

        # Try from package __file__
        try:
            import specify_cli

            pkg_dir = Path(specify_cli.__file__).parent
            template_file = pkg_dir.joinpath(*path_parts, self.SOURCE_FILENAME)
            if template_file.exists():
                return template_file
        except (ImportError, AttributeError):
            pass

        # Fallback: development repo
        try:
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                template_file = (
                    parent / "src" / "specify_cli" / Path(*path_parts) / self.SOURCE_FILENAME
                )
                pyproject = parent / "pyproject.toml"
                if template_file.exists() and pyproject.exists():
                    try:
                        content = pyproject.read_text(encoding="utf-8-sig")
                        if "spec-kitty-cli" in content:
                            return template_file
                    except OSError:
                        pass
        except OSError:
            pass

        return None
