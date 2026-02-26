"""Integration tests for spec storage context output (WP06 / T030-T031).

Tests verify that the spec storage context info module correctly
reports branch, path, and health information for real git repositories.

Discoverable via: ``pytest tests/integration -k "context_output"``

All tests use real temporary git repos (no git mocking).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_context_info import (
    SpecStorageContextInfo,
    get_spec_storage_context_info,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    save_spec_storage_config,
)
from specify_cli.core.spec_worktree_discovery import HEALTH_HEALTHY


# ============================================================================
# Helpers
# ============================================================================


def _git(
    args: list[str], cwd: Path, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _init_repo(path: Path) -> Path:
    """Create and initialize a git repository with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init"], cwd=path)
    _git(["config", "user.name", "Test User"], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    (path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    _git(["add", "."], cwd=path)
    _git(["commit", "-m", "Initial commit"], cwd=path)
    _git(["branch", "-M", "main"], cwd=path)
    return path


def _setup_healthy_spec_storage(repo: Path) -> SpecStorageConfig:
    """Configure a repo with a healthy orphan spec branch + worktree."""
    (repo / ".kittify").mkdir(parents=True, exist_ok=True)

    # Create orphan branch
    _git(["checkout", "--orphan", "kitty-specs"], cwd=repo)
    (repo / "README.md").unlink(missing_ok=True)
    _git(["rm", "-rf", "."], cwd=repo, check=False)
    specs_dir = repo / "001-test-feature"
    specs_dir.mkdir(parents=True)
    (specs_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "Initial spec commit"], cwd=repo)

    _git(["checkout", "main"], cwd=repo)

    wt_path = repo / "kitty-specs"
    _git(["worktree", "add", str(wt_path), "kitty-specs"], cwd=repo)

    config = SpecStorageConfig(
        branch_name="kitty-specs",
        worktree_path="kitty-specs",
        auto_push=False,
        is_defaulted=False,
    )
    save_spec_storage_config(repo, config)
    return config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def empty_repo(tmp_path: Path) -> Path:
    """Clean repo without spec storage config."""
    return _init_repo(tmp_path / "repo")


@pytest.fixture()
def healthy_repo(tmp_path: Path) -> Path:
    """Repo with healthy spec storage."""
    repo = _init_repo(tmp_path / "repo")
    _setup_healthy_spec_storage(repo)
    return repo


# ============================================================================
# Test: Context info with healthy topology
# ============================================================================


class TestContextHealthyTopology:
    """Context output for fully configured, healthy repos."""

    def test_reports_configured_true(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        assert info.configured is True

    def test_reports_branch_name(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        assert info.branch_name == "kitty-specs"

    def test_reports_worktree_path(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        assert info.worktree_path is not None
        assert Path(info.worktree_path).is_absolute()

    def test_reports_healthy_status(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        assert info.health_status == HEALTH_HEALTHY

    def test_to_dict_has_all_keys(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        d = info.to_dict()
        assert "configured" in d
        assert "branch_name" in d
        assert "worktree_path" in d
        assert "health_status" in d


# ============================================================================
# Test: Context info without spec_storage config
# ============================================================================


class TestContextNotConfigured:
    """Context output for legacy repos without spec_storage."""

    def test_reports_configured_false(self, empty_repo: Path):
        info = get_spec_storage_context_info(empty_repo)
        assert info.configured is False

    def test_default_branch_name(self, empty_repo: Path):
        info = get_spec_storage_context_info(empty_repo)
        assert info.branch_name == "kitty-specs"

    def test_no_crash_on_legacy(self, empty_repo: Path):
        """Should not crash when no config exists."""
        info = get_spec_storage_context_info(empty_repo)
        assert isinstance(info, SpecStorageContextInfo)


# ============================================================================
# Test: JSON output shape stability
# ============================================================================


class TestContextJsonOutputShape:
    """Verify JSON output shape for automation consumers."""

    def test_configured_json_shape(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo)
        d = info.to_dict()
        assert isinstance(d["configured"], bool)
        assert isinstance(d["branch_name"], str)
        assert isinstance(d["worktree_path"], str)
        assert isinstance(d["health_status"], str)

    def test_unconfigured_json_shape(self, empty_repo: Path):
        info = get_spec_storage_context_info(empty_repo)
        d = info.to_dict()
        assert isinstance(d["configured"], bool)
        assert isinstance(d["branch_name"], str)
        # worktree_path and health_status may be None for unconfigured
        assert d["worktree_path"] is None or isinstance(d["worktree_path"], str)
        assert d["health_status"] is None or isinstance(d["health_status"], str)


# ============================================================================
# Test: Skip discovery mode
# ============================================================================


class TestContextSkipDiscovery:
    """Verify run_discovery=False skips git subprocess calls."""

    def test_skip_discovery_no_health(self, healthy_repo: Path):
        info = get_spec_storage_context_info(healthy_repo, run_discovery=False)
        assert info.health_status is None
        assert info.configured is True
        assert info.branch_name == "kitty-specs"
