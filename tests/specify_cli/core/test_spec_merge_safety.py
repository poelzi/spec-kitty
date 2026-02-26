"""Unit tests for spec merge safety utilities (WP06 / T028-T029).

Tests cover:
- Exclusion pattern generation from default and custom config
- Path filtering correctly removes kitty-specs/ paths
- Non-spec paths pass through unfiltered
- Custom worktree path exclusion works
- Edge cases: empty paths, Windows separators, deeply nested paths
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specify_cli.core.spec_merge_safety import (
    filter_merge_paths,
    get_spec_path_exclusion_patterns,
    get_spec_path_exclusion_patterns_from_config,
    should_exclude_from_merge,
)
from specify_cli.core.spec_storage_config import SpecStorageConfig


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Create a minimal repo root with .kittify/ directory."""
    kittify = tmp_path / ".kittify"
    kittify.mkdir()
    return tmp_path


@pytest.fixture
def repo_with_default_config(repo_root: Path) -> Path:
    """Repo with default spec_storage config (kitty-specs)."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "spec_storage:\n"
        "  branch_name: kitty-specs\n"
        "  worktree_path: kitty-specs\n"
        "  auto_push: false\n",
        encoding="utf-8",
    )
    return repo_root


@pytest.fixture
def repo_with_custom_config(repo_root: Path) -> Path:
    """Repo with custom spec_storage worktree path."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "spec_storage:\n"
        "  branch_name: my-specs\n"
        "  worktree_path: .specs-worktree\n"
        "  auto_push: false\n",
        encoding="utf-8",
    )
    return repo_root


@pytest.fixture
def repo_without_config(repo_root: Path) -> Path:
    """Repo without spec_storage section (legacy)."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "vcs:\n"
        "  type: git\n",
        encoding="utf-8",
    )
    return repo_root


# ============================================================================
# Test: get_spec_path_exclusion_patterns
# ============================================================================


class TestGetSpecPathExclusionPatterns:
    """Tests for exclusion pattern generation."""

    def test_default_config_returns_kitty_specs_patterns(
        self, repo_with_default_config: Path
    ):
        patterns = get_spec_path_exclusion_patterns(repo_with_default_config)
        assert "kitty-specs" in patterns
        assert "kitty-specs/*" in patterns
        assert len(patterns) == 2

    def test_custom_config_returns_custom_patterns(
        self, repo_with_custom_config: Path
    ):
        patterns = get_spec_path_exclusion_patterns(repo_with_custom_config)
        assert ".specs-worktree" in patterns
        assert ".specs-worktree/*" in patterns
        assert len(patterns) == 2

    def test_legacy_repo_falls_back_to_default(
        self, repo_without_config: Path
    ):
        """Legacy repos without spec_storage should use default 'kitty-specs'."""
        patterns = get_spec_path_exclusion_patterns(repo_without_config)
        assert "kitty-specs" in patterns
        assert "kitty-specs/*" in patterns

    def test_missing_config_file_falls_back_to_default(self, tmp_path: Path):
        """Repo without any config file should use default."""
        patterns = get_spec_path_exclusion_patterns(tmp_path)
        assert "kitty-specs" in patterns
        assert "kitty-specs/*" in patterns


class TestGetSpecPathExclusionPatternsFromConfig:
    """Tests for pattern generation from pre-loaded config."""

    def test_from_default_config(self):
        config = SpecStorageConfig()
        patterns = get_spec_path_exclusion_patterns_from_config(config)
        assert "kitty-specs" in patterns
        assert "kitty-specs/*" in patterns

    def test_from_custom_config(self):
        config = SpecStorageConfig(worktree_path="my-custom-specs")
        patterns = get_spec_path_exclusion_patterns_from_config(config)
        assert "my-custom-specs" in patterns
        assert "my-custom-specs/*" in patterns

    def test_trailing_slash_stripped(self):
        config = SpecStorageConfig(worktree_path="specs-dir/")
        patterns = get_spec_path_exclusion_patterns_from_config(config)
        assert "specs-dir" in patterns
        assert "specs-dir/*" in patterns


# ============================================================================
# Test: should_exclude_from_merge
# ============================================================================


class TestShouldExcludeFromMerge:
    """Tests for individual path exclusion checks."""

    @pytest.fixture
    def default_patterns(self) -> list[str]:
        return ["kitty-specs", "kitty-specs/*"]

    def test_exact_directory_match(self, default_patterns):
        assert should_exclude_from_merge("kitty-specs", default_patterns) is True

    def test_direct_child(self, default_patterns):
        assert should_exclude_from_merge("kitty-specs/001-feature", default_patterns) is True

    def test_deeply_nested_path(self, default_patterns):
        assert should_exclude_from_merge(
            "kitty-specs/001-feature/tasks/WP01.md", default_patterns
        ) is True

    def test_non_spec_path_passes_through(self, default_patterns):
        assert should_exclude_from_merge("src/main.py", default_patterns) is False

    def test_similar_prefix_not_excluded(self, default_patterns):
        """'kitty-specs-extra' should NOT match 'kitty-specs'."""
        assert should_exclude_from_merge("kitty-specs-extra/file.txt", default_patterns) is False

    def test_unrelated_path(self, default_patterns):
        assert should_exclude_from_merge("README.md", default_patterns) is False

    def test_empty_path(self, default_patterns):
        assert should_exclude_from_merge("", default_patterns) is False

    def test_root_file(self, default_patterns):
        assert should_exclude_from_merge("pyproject.toml", default_patterns) is False

    def test_custom_pattern(self):
        patterns = [".specs-worktree", ".specs-worktree/*"]
        assert should_exclude_from_merge(".specs-worktree/plan.md", patterns) is True
        assert should_exclude_from_merge("kitty-specs/plan.md", patterns) is False

    def test_windows_separators(self, default_patterns):
        """Backslash separators should be normalised."""
        assert should_exclude_from_merge(
            "kitty-specs\\001-feature\\plan.md", default_patterns
        ) is True

    def test_empty_patterns_list(self):
        """No patterns means nothing is excluded."""
        assert should_exclude_from_merge("kitty-specs/foo", []) is False


# ============================================================================
# Test: filter_merge_paths
# ============================================================================


class TestFilterMergePaths:
    """Tests for batch path filtering."""

    @pytest.fixture
    def default_patterns(self) -> list[str]:
        return ["kitty-specs", "kitty-specs/*"]

    def test_removes_spec_paths(self, default_patterns):
        paths = [
            "src/main.py",
            "kitty-specs/001-feature/spec.md",
            "kitty-specs/001-feature/plan.md",
            "README.md",
            "tests/test_core.py",
        ]
        result = filter_merge_paths(paths, default_patterns)
        assert result == ["src/main.py", "README.md", "tests/test_core.py"]

    def test_empty_input(self, default_patterns):
        assert filter_merge_paths([], default_patterns) == []

    def test_all_spec_paths_removed(self, default_patterns):
        paths = [
            "kitty-specs/spec.md",
            "kitty-specs/plan.md",
            "kitty-specs/tasks/WP01.md",
        ]
        assert filter_merge_paths(paths, default_patterns) == []

    def test_no_spec_paths_unchanged(self, default_patterns):
        paths = ["src/main.py", "README.md", "tests/test.py"]
        result = filter_merge_paths(paths, default_patterns)
        assert result == paths

    def test_preserves_order(self, default_patterns):
        paths = [
            "z_last.py",
            "kitty-specs/plan.md",
            "a_first.py",
            "kitty-specs/spec.md",
            "m_middle.py",
        ]
        result = filter_merge_paths(paths, default_patterns)
        assert result == ["z_last.py", "a_first.py", "m_middle.py"]

    def test_custom_worktree_path(self):
        patterns = [".specs", ".specs/*"]
        paths = [
            "src/app.py",
            ".specs/001-feat/spec.md",
            ".specs/001-feat/tasks/WP01.md",
            "docs/README.md",
        ]
        result = filter_merge_paths(paths, patterns)
        assert result == ["src/app.py", "docs/README.md"]

    def test_mixed_spec_and_regular_paths(self, default_patterns):
        """Ensure paths that start with 'kitty-specs' prefix but are actually
        different directories are not excluded."""
        paths = [
            "kitty-specs/plan.md",
            "kitty-specs-backup/old.md",
            "kitty-specs-v2/new.md",
        ]
        result = filter_merge_paths(paths, default_patterns)
        assert result == ["kitty-specs-backup/old.md", "kitty-specs-v2/new.md"]
