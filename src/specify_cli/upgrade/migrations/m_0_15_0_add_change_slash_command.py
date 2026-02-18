"""Migration: Add spec-kitty.change and spec-kitty.integrate slash commands.

Feature 029 introduced the /spec-kitty.change mid-stream change command with
a source template at missions/software-dev/command-templates/change.md.

The landing branch workflow (v0.15.0) introduced /spec-kitty.integrate with
a source template at templates/command-templates/integrate.md.

This migration copies both templates to all configured agent directories.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..registry import MigrationRegistry
from .base import BaseMigration, MigrationResult
from .m_0_9_1_complete_lane_migration import get_agent_dirs_for_project


@MigrationRegistry.register
class AddChangeSlashCommandMigration(BaseMigration):
    """Deploy spec-kitty.change.md and spec-kitty.integrate.md to all configured agents."""

    migration_id = "0.15.0_add_change_slash_command"
    description = "Add /spec-kitty.change and /spec-kitty.integrate slash commands to agent directories"
    target_version = "0.15.0"

    # Templates to deploy: (dest_filename, source_filename, source_search_paths)
    # Each tuple: (agent file name, source file name, list of package-relative search dirs)
    TEMPLATES = [
        (
            "spec-kitty.change.md",
            "change.md",
            [("missions", "software-dev", "command-templates")],
        ),
        (
            "spec-kitty.integrate.md",
            "integrate.md",
            [
                ("missions", "software-dev", "command-templates"),
                ("templates", "command-templates"),
            ],
        ),
    ]

    def detect(self, project_path: Path) -> bool:
        """Return True if any template is missing from any configured agent."""
        agent_dirs = get_agent_dirs_for_project(project_path)

        for agent_root, subdir in agent_dirs:
            agent_dir = project_path / agent_root / subdir
            if not agent_dir.exists():
                continue

            for dest_name, _, _ in self.TEMPLATES:
                if not (agent_dir / dest_name).exists():
                    return True

        return False

    def can_apply(self, project_path: Path) -> tuple[bool, str]:
        """Verify at least one source template is available."""
        for dest_name, source_name, search_paths in self.TEMPLATES:
            template = self._find_package_template(source_name, search_paths)
            if template is None:
                return (
                    False,
                    f"Could not locate package {source_name} template. "
                    "Run 'spec-kitty upgrade' again after installation.",
                )
        return True, ""

    def apply(self, project_path: Path, dry_run: bool = False) -> MigrationResult:
        """Copy templates to all configured agent directories."""
        changes: list[str] = []
        errors: list[str] = []

        # Resolve all source templates first
        resolved_templates: list[tuple[str, Path]] = []
        for dest_name, source_name, search_paths in self.TEMPLATES:
            package_template = self._find_package_template(source_name, search_paths)
            if package_template is None:
                errors.append(f"Could not locate package {source_name} template")
                continue
            resolved_templates.append((dest_name, package_template))

        if errors:
            return MigrationResult(success=False, errors=errors)

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

            for dest_name, package_template in resolved_templates:
                dest = agent_dir / dest_name

                # Skip if already exists with correct content
                if dest.exists():
                    try:
                        if dest.read_text(
                            encoding="utf-8"
                        ) == package_template.read_text(encoding="utf-8"):
                            continue
                    except OSError:
                        pass

                if dry_run:
                    action = "Would update" if dest.exists() else "Would create"
                    changes.append(f"{action} {agent_root}/{subdir}/{dest_name}")
                else:
                    try:
                        shutil.copy2(package_template, dest)
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

    def _find_package_template(
        self, source_filename: str, search_paths: list[tuple[str, ...]]
    ) -> Path | None:
        """Locate a template file in the installed package or local repo."""
        for path_parts in search_paths:
            found = self._search_template(source_filename, path_parts)
            if found:
                return found
        return None

    def _search_template(
        self, source_filename: str, path_parts: tuple[str, ...]
    ) -> Path | None:
        """Search for a template in a specific package-relative path."""
        # Try importlib.resources
        try:
            from importlib.resources import files

            pkg_files = files("specify_cli")
            template_path = pkg_files.joinpath(*path_parts, source_filename)
            resolved = Path(str(template_path))
            if resolved.exists():
                return resolved
        except (ImportError, TypeError, AttributeError):
            pass

        # Try from package __file__
        try:
            import specify_cli

            pkg_dir = Path(specify_cli.__file__).parent
            template_file = pkg_dir.joinpath(*path_parts, source_filename)
            if template_file.exists():
                return template_file
        except (ImportError, AttributeError):
            pass

        # Fallback: development repo
        try:
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                template_file = (
                    parent / "src" / "specify_cli" / Path(*path_parts) / source_filename
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
