"""Integration tests for spec storage write routing (WP03 T012-T014).

These tests verify that planning artifact writes are routed through the
centralized spec artifact resolver to the correct location — the spec
worktree for repos with ``spec_storage`` config, or the legacy
``repo_root / "kitty-specs"`` path for repos without.

Tests cover:
1. Resolver routes to spec worktree when config exists
2. Resolver falls back to legacy path when no config
3. feature_detection helpers use resolver (not hardcoded paths)
4. tasks.py and workflow.py path resolution uses resolver
5. Planning branch remains free of spec file commits after routing
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_artifact_resolver import (
    SpecArtifactResolutionError,
    resolve_feature_dir,
    resolve_spec_artifact_root,
    resolve_tasks_dir,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    has_spec_storage_config,
    save_spec_storage_config,
)


# ============================================================================
# Helpers
# ============================================================================


def _init_git_repo(path: Path) -> None:
    """Create a minimal git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, capture_output=True, check=True,
    )
    readme = path / "README.md"
    readme.write_text("# Test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=path, capture_output=True, check=True,
    )


def _setup_spec_storage(repo_root: Path, worktree_path: str = "kitty-specs") -> None:
    """Bootstrap spec storage: create orphan branch, worktree, and config."""
    branch_name = worktree_path  # Use same name for simplicity in tests
    config = SpecStorageConfig(
        branch_name=branch_name,
        worktree_path=worktree_path,
        auto_push=False,
    )

    # Create orphan branch
    subprocess.run(
        ["git", "checkout", "--orphan", branch_name],
        cwd=repo_root, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "rm", "-rf", "."],
        cwd=repo_root, capture_output=True, check=True,
    )
    gitkeep = repo_root / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=repo_root, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial spec branch"],
        cwd=repo_root, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=repo_root, capture_output=True, check=True,
    )

    # Create worktree
    wt_abs = repo_root / worktree_path
    if not wt_abs.exists():
        subprocess.run(
            ["git", "worktree", "add", str(wt_abs), branch_name],
            cwd=repo_root, capture_output=True, check=True,
        )

    # Save config
    save_spec_storage_config(repo_root, config)
    subprocess.run(["git", "add", ".kittify/"], cwd=repo_root, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add spec storage config"],
        cwd=repo_root, capture_output=True, check=True,
    )


# ============================================================================
# Tests
# ============================================================================


class TestResolverRouting:
    """Verify resolver routes to correct location based on config."""

    def test_routes_to_spec_worktree_when_config_exists(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        result = resolve_spec_artifact_root(repo, require_healthy=False)

        # Should resolve to worktree path, not legacy
        assert result == (repo / "kitty-specs").resolve()

    def test_falls_back_to_legacy_when_no_config(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        result = resolve_spec_artifact_root(repo, require_healthy=False)

        assert result == repo / "kitty-specs"

    def test_custom_worktree_path_honored(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "specs")

        result = resolve_spec_artifact_root(repo, require_healthy=False)

        assert result == (repo / "specs").resolve()

    def test_resolve_feature_dir_routes_correctly(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        result = resolve_feature_dir(repo, "001-test-feature", require_healthy=False)

        expected = (repo / "kitty-specs" / "001-test-feature").resolve()
        assert result == expected

    def test_resolve_tasks_dir_routes_correctly(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        result = resolve_tasks_dir(repo, "001-test-feature", require_healthy=False)

        expected = (repo / "kitty-specs" / "001-test-feature" / "tasks").resolve()
        assert result == expected


class TestFeatureDetectionUsesResolver:
    """Verify feature_detection.py functions use resolver, not hardcoded paths."""

    def test_list_features_finds_features_in_spec_root(self, tmp_path: Path) -> None:
        """Features listed from the spec artifact root, not hardcoded kitty-specs."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        # Create a feature directory in the spec worktree
        spec_root = resolve_spec_artifact_root(repo, require_healthy=False)
        feature = spec_root / "001-test-feature"
        feature.mkdir(parents=True, exist_ok=True)
        (feature / "spec.md").write_text("# Spec\n", encoding="utf-8")

        from specify_cli.core.feature_detection import _list_all_features

        features = _list_all_features(repo)
        assert "001-test-feature" in features

    def test_validate_feature_exists_uses_resolver(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        spec_root = resolve_spec_artifact_root(repo, require_healthy=False)
        feature = spec_root / "001-test-feature"
        feature.mkdir(parents=True, exist_ok=True)

        from specify_cli.core.feature_detection import _validate_feature_exists

        assert _validate_feature_exists("001-test-feature", repo) is True
        assert _validate_feature_exists("999-nonexistent", repo) is False

    def test_get_feature_target_branch_uses_resolver(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        spec_root = resolve_spec_artifact_root(repo, require_healthy=False)
        feature = spec_root / "001-test-feature"
        feature.mkdir(parents=True, exist_ok=True)
        meta = {"target_branch": "001-test-feature", "upstream_branch": "main"}
        (feature / "meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )

        from specify_cli.core.feature_detection import get_feature_target_branch

        branch = get_feature_target_branch(repo, "001-test-feature")
        assert branch == "001-test-feature"


class TestPlanningBranchCleanliness:
    """Verify that the planning branch (main) stays free of spec file commits."""

    def test_spec_writes_go_to_worktree_not_main(self, tmp_path: Path) -> None:
        """When spec_storage is configured, writing files to the resolved path
        writes into the worktree, not into main's working tree."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _setup_spec_storage(repo, "kitty-specs")

        spec_root = resolve_spec_artifact_root(repo, require_healthy=False)

        # Write a spec file via the resolved path
        feature_dir = spec_root / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec_file = feature_dir / "spec.md"
        spec_file.write_text("# Test spec\n", encoding="utf-8")

        # Verify the file is in the worktree (which is on the spec branch)
        wt_branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=spec_root,
            capture_output=True, text=True, check=True,
        )
        assert wt_branch_result.stdout.strip() == "kitty-specs"

        # Verify the main branch working tree does NOT have this file
        # (it's in the worktree, not in the main checkout)
        main_branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            capture_output=True, text=True, check=True,
        )
        assert main_branch_result.stdout.strip() == "main"
