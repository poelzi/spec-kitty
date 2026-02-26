"""Unit tests for spec_artifact_resolver module.

Tests cover:
- T012: Centralized planning-artifact root resolver
  - Legacy repos (no spec_storage config) → repo_root / "kitty-specs"
  - New repos with spec_storage config → worktree path
  - Health validation (require_healthy flag)
  - Feature and task directory resolution
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specify_cli.core.spec_artifact_resolver import (
    SpecArtifactResolutionError,
    resolve_feature_dir,
    resolve_spec_artifact_root,
    resolve_tasks_dir,
)
from specify_cli.core.spec_storage_config import SpecStorageConfig
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    SpecWorktreeState,
)


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
def legacy_repo(repo_root: Path) -> Path:
    """Create a legacy repo without spec_storage config."""
    # Write a config.yaml without spec_storage
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "vcs:\n"
        "  type: git\n"
        "agents:\n"
        "  available:\n"
        "    - claude\n",
        encoding="utf-8",
    )
    return repo_root


@pytest.fixture
def new_repo(repo_root: Path) -> Path:
    """Create a new repo with spec_storage config."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "vcs:\n"
        "  type: git\n"
        "spec_storage:\n"
        "  branch_name: kitty-specs\n"
        "  worktree_path: kitty-specs\n"
        "  auto_push: false\n",
        encoding="utf-8",
    )
    return repo_root


# ============================================================================
# T012 - resolve_spec_artifact_root
# ============================================================================


class TestResolveSpecArtifactRoot:
    """Tests for resolve_spec_artifact_root()."""

    def test_legacy_repo_returns_kitty_specs(self, legacy_repo: Path) -> None:
        """Legacy repos without spec_storage config return repo_root/kitty-specs."""
        result = resolve_spec_artifact_root(legacy_repo)
        assert result == legacy_repo / "kitty-specs"

    def test_legacy_repo_no_config_file(self, repo_root: Path) -> None:
        """Repos without any config.yaml return repo_root/kitty-specs."""
        # Remove the .kittify dir entirely (no config at all)
        result = resolve_spec_artifact_root(repo_root)
        assert result == repo_root / "kitty-specs"

    @patch("specify_cli.core.spec_artifact_resolver.discover_spec_worktree")
    def test_new_repo_healthy_worktree(
        self, mock_discover: MagicMock, new_repo: Path
    ) -> None:
        """New repos with healthy worktree return worktree abs path."""
        mock_discover.return_value = SpecWorktreeState(
            path=str(new_repo / "kitty-specs"),
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_HEALTHY,
        )
        result = resolve_spec_artifact_root(new_repo)
        expected = (new_repo / "kitty-specs").resolve()
        assert result == expected
        mock_discover.assert_called_once()

    @patch("specify_cli.core.spec_artifact_resolver.discover_spec_worktree")
    def test_new_repo_unhealthy_worktree_require_healthy(
        self, mock_discover: MagicMock, new_repo: Path
    ) -> None:
        """Raises error when worktree is unhealthy and require_healthy=True."""
        mock_discover.return_value = SpecWorktreeState(
            path=str(new_repo / "kitty-specs"),
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_MISSING_PATH,
        )
        with pytest.raises(SpecArtifactResolutionError, match="not healthy"):
            resolve_spec_artifact_root(new_repo, require_healthy=True)

    @patch("specify_cli.core.spec_artifact_resolver.discover_spec_worktree")
    def test_new_repo_unhealthy_worktree_skip_health(
        self, mock_discover: MagicMock, new_repo: Path
    ) -> None:
        """Returns path when require_healthy=False even if worktree unhealthy."""
        result = resolve_spec_artifact_root(new_repo, require_healthy=False)
        expected = (new_repo / "kitty-specs").resolve()
        assert result == expected
        mock_discover.assert_not_called()

    def test_legacy_repo_require_healthy_is_noop(self, legacy_repo: Path) -> None:
        """Legacy repos never check health (no worktree to check)."""
        # Should not raise even with require_healthy=True
        result = resolve_spec_artifact_root(legacy_repo, require_healthy=True)
        assert result == legacy_repo / "kitty-specs"


# ============================================================================
# T012 - resolve_feature_dir
# ============================================================================


class TestResolveFeatureDir:
    """Tests for resolve_feature_dir()."""

    def test_legacy_repo_feature_dir(self, legacy_repo: Path) -> None:
        """Feature dir is under kitty-specs for legacy repos."""
        result = resolve_feature_dir(legacy_repo, "001-my-feature")
        assert result == legacy_repo / "kitty-specs" / "001-my-feature"

    @patch("specify_cli.core.spec_artifact_resolver.discover_spec_worktree")
    def test_new_repo_feature_dir(
        self, mock_discover: MagicMock, new_repo: Path
    ) -> None:
        """Feature dir is under worktree for new repos."""
        mock_discover.return_value = SpecWorktreeState(
            path=str(new_repo / "kitty-specs"),
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_HEALTHY,
        )
        result = resolve_feature_dir(new_repo, "001-my-feature")
        expected = (new_repo / "kitty-specs").resolve() / "001-my-feature"
        assert result == expected


# ============================================================================
# T012 - resolve_tasks_dir
# ============================================================================


class TestResolveTasksDir:
    """Tests for resolve_tasks_dir()."""

    def test_legacy_repo_tasks_dir(self, legacy_repo: Path) -> None:
        """Tasks dir is under feature dir for legacy repos."""
        result = resolve_tasks_dir(legacy_repo, "001-my-feature")
        assert result == legacy_repo / "kitty-specs" / "001-my-feature" / "tasks"

    @patch("specify_cli.core.spec_artifact_resolver.discover_spec_worktree")
    def test_new_repo_tasks_dir(
        self, mock_discover: MagicMock, new_repo: Path
    ) -> None:
        """Tasks dir is under worktree for new repos."""
        mock_discover.return_value = SpecWorktreeState(
            path=str(new_repo / "kitty-specs"),
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_HEALTHY,
        )
        result = resolve_tasks_dir(new_repo, "002-another")
        expected = (new_repo / "kitty-specs").resolve() / "002-another" / "tasks"
        assert result == expected

    def test_tasks_dir_passes_require_healthy(self, legacy_repo: Path) -> None:
        """require_healthy is passed through to the resolver."""
        # Legacy repos don't check health, so this just verifies the kwarg flows
        result = resolve_tasks_dir(
            legacy_repo, "001-my-feature", require_healthy=False
        )
        assert result == legacy_repo / "kitty-specs" / "001-my-feature" / "tasks"
