"""Unit tests for spec storage context info exposure (WP06 / T030-T031).

Tests cover:
- Context info generation with healthy topology
- Context info generation without spec_storage config
- Fields are present and correctly typed
- Serialisation to dict for JSON output
- Graceful handling of discovery failures
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from specify_cli.core.spec_context_info import (
    SpecStorageContextInfo,
    get_spec_storage_context_info,
)
from specify_cli.core.spec_storage_config import SpecStorageConfig
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    HEALTH_MISSING_PATH,
    HEALTH_MISSING_REGISTRATION,
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
def repo_with_config(repo_root: Path) -> Path:
    """Repo with spec_storage config."""
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
    """Repo with custom spec_storage config."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "spec_storage:\n"
        "  branch_name: specs-branch\n"
        "  worktree_path: .my-specs\n"
        "  auto_push: true\n",
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


@pytest.fixture
def healthy_worktree_state() -> SpecWorktreeState:
    """A healthy worktree state."""
    return SpecWorktreeState(
        path="/fake/repo/kitty-specs",
        registered=True,
        branch_name="kitty-specs",
        is_clean=True,
        has_manual_changes=False,
        health_status=HEALTH_HEALTHY,
    )


@pytest.fixture
def missing_worktree_state() -> SpecWorktreeState:
    """A worktree state with missing registration."""
    return SpecWorktreeState(
        path="/fake/repo/kitty-specs",
        registered=False,
        branch_name=None,
        is_clean=True,
        has_manual_changes=False,
        health_status=HEALTH_MISSING_REGISTRATION,
    )


# ============================================================================
# Test: SpecStorageContextInfo dataclass
# ============================================================================


class TestSpecStorageContextInfo:
    """Tests for the context info data model."""

    def test_fields_present(self):
        info = SpecStorageContextInfo(
            configured=True,
            branch_name="kitty-specs",
            worktree_path="/repo/kitty-specs",
            health_status="healthy",
        )
        assert info.configured is True
        assert info.branch_name == "kitty-specs"
        assert info.worktree_path == "/repo/kitty-specs"
        assert info.health_status == "healthy"

    def test_unconfigured_fields(self):
        info = SpecStorageContextInfo(
            configured=False,
            branch_name="kitty-specs",
            worktree_path=None,
            health_status=None,
        )
        assert info.configured is False
        assert info.worktree_path is None
        assert info.health_status is None

    def test_to_dict(self):
        info = SpecStorageContextInfo(
            configured=True,
            branch_name="my-specs",
            worktree_path="/repo/my-specs",
            health_status="healthy",
        )
        d = info.to_dict()
        assert isinstance(d, dict)
        assert d["configured"] is True
        assert d["branch_name"] == "my-specs"
        assert d["worktree_path"] == "/repo/my-specs"
        assert d["health_status"] == "healthy"

    def test_to_dict_with_none_values(self):
        info = SpecStorageContextInfo(
            configured=False,
            branch_name="kitty-specs",
            worktree_path=None,
            health_status=None,
        )
        d = info.to_dict()
        assert d["worktree_path"] is None
        assert d["health_status"] is None

    def test_field_types(self):
        info = SpecStorageContextInfo(
            configured=True,
            branch_name="kitty-specs",
            worktree_path="/repo/kitty-specs",
            health_status="healthy",
        )
        assert isinstance(info.configured, bool)
        assert isinstance(info.branch_name, str)
        assert isinstance(info.worktree_path, str)
        assert isinstance(info.health_status, str)


# ============================================================================
# Test: get_spec_storage_context_info
# ============================================================================


class TestGetSpecStorageContextInfo:
    """Tests for the context info builder function."""

    def test_configured_repo_with_healthy_worktree(
        self, repo_with_config: Path, healthy_worktree_state: SpecWorktreeState
    ):
        """Configured repo with healthy discovery should report all fields."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
            return_value=healthy_worktree_state,
        ):
            info = get_spec_storage_context_info(repo_with_config)

        assert info.configured is True
        assert info.branch_name == "kitty-specs"
        assert info.worktree_path is not None
        assert info.health_status == HEALTH_HEALTHY

    def test_configured_repo_with_custom_branch(
        self, repo_with_custom_config: Path, healthy_worktree_state: SpecWorktreeState
    ):
        """Custom config should use custom branch name."""
        custom_state = SpecWorktreeState(
            path=str(repo_with_custom_config / ".my-specs"),
            registered=True,
            branch_name="specs-branch",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_HEALTHY,
        )
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
            return_value=custom_state,
        ):
            info = get_spec_storage_context_info(repo_with_custom_config)

        assert info.configured is True
        assert info.branch_name == "specs-branch"
        assert info.health_status == HEALTH_HEALTHY

    def test_unconfigured_repo(self, repo_without_config: Path):
        """Legacy repo without spec_storage should report configured=False."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
        ) as mock_discover:
            mock_discover.return_value = SpecWorktreeState(
                path=str(repo_without_config / "kitty-specs"),
                registered=False,
                branch_name=None,
                is_clean=True,
                has_manual_changes=False,
                health_status=HEALTH_MISSING_REGISTRATION,
            )
            info = get_spec_storage_context_info(repo_without_config)

        assert info.configured is False
        # Should still have sensible defaults
        assert info.branch_name == "kitty-specs"

    def test_missing_config_file(self, tmp_path: Path):
        """Repo with no config file at all should report configured=False."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
        ) as mock_discover:
            mock_discover.return_value = SpecWorktreeState(
                path=str(tmp_path / "kitty-specs"),
                registered=False,
                branch_name=None,
                is_clean=True,
                has_manual_changes=False,
                health_status=HEALTH_MISSING_REGISTRATION,
            )
            info = get_spec_storage_context_info(tmp_path)

        assert info.configured is False
        assert info.branch_name == "kitty-specs"

    def test_skip_discovery(self, repo_with_config: Path):
        """With run_discovery=False, health_status should be None."""
        info = get_spec_storage_context_info(
            repo_with_config, run_discovery=False
        )
        assert info.configured is True
        assert info.branch_name == "kitty-specs"
        assert info.health_status is None

    def test_discovery_failure_graceful(self, repo_with_config: Path):
        """If discovery raises, health_status should be None (not crash)."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
            side_effect=RuntimeError("git not available"),
        ):
            info = get_spec_storage_context_info(repo_with_config)

        assert info.configured is True
        assert info.branch_name == "kitty-specs"
        assert info.health_status is None

    def test_worktree_path_is_absolute(self, repo_with_config: Path):
        """worktree_path should be an absolute path string."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
        ) as mock_discover:
            mock_discover.return_value = SpecWorktreeState(
                path=str(repo_with_config / "kitty-specs"),
                registered=True,
                branch_name="kitty-specs",
                is_clean=True,
                has_manual_changes=False,
                health_status=HEALTH_HEALTHY,
            )
            info = get_spec_storage_context_info(repo_with_config)

        assert info.worktree_path is not None
        assert Path(info.worktree_path).is_absolute()

    def test_to_dict_integration(
        self, repo_with_config: Path, healthy_worktree_state: SpecWorktreeState
    ):
        """to_dict should work on real context info output."""
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
            return_value=healthy_worktree_state,
        ):
            info = get_spec_storage_context_info(repo_with_config)

        d = info.to_dict()
        assert "configured" in d
        assert "branch_name" in d
        assert "worktree_path" in d
        assert "health_status" in d

    def test_missing_path_health_status(self, repo_with_config: Path):
        """Health status should reflect discovery state accurately."""
        missing_state = SpecWorktreeState(
            path="/fake/kitty-specs",
            registered=True,
            branch_name="kitty-specs",
            is_clean=True,
            has_manual_changes=False,
            health_status=HEALTH_MISSING_PATH,
        )
        with patch(
            "specify_cli.core.spec_context_info.discover_spec_worktree",
            return_value=missing_state,
        ):
            info = get_spec_storage_context_info(repo_with_config)

        assert info.health_status == HEALTH_MISSING_PATH
