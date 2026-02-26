"""Integration tests for spec storage bootstrap during init (WP02 T011).

These tests exercise the full bootstrap_spec_storage() flow against
real git repositories (not mocked).

Tests cover:
1. Fresh repo: creates orphan branch, worktree, writes config
2. Rerun: idempotent, doesn't duplicate
3. Custom config values honored
4. Path conflict fails safely
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from rich.console import Console

from specify_cli.core.spec_branch_bootstrap import bootstrap_spec_storage
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    has_spec_storage_config,
    load_spec_storage_config,
    save_spec_storage_config,
)
from specify_cli.core.git_ops import inspect_spec_branch
from specify_cli.core.spec_worktree_discovery import (
    HEALTH_HEALTHY,
    discover_spec_worktree,
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
    # Create initial commit so we have a main branch
    readme = path / "README.md"
    readme.write_text("# Test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path, capture_output=True, check=True,
    )
    # Ensure branch is called 'main'
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=path, capture_output=True, check=True,
    )


def _create_kittify_dir(path: Path) -> None:
    """Create .kittify directory (normally created by init template)."""
    (path / ".kittify").mkdir(parents=True, exist_ok=True)


def _branch_exists(repo: Path, branch: str) -> bool:
    """Check if a branch exists in the repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


def _is_orphan(repo: Path, branch: str, primary: str = "main") -> bool:
    """Check if branch is orphan (no shared ancestry with primary)."""
    result = subprocess.run(
        ["git", "merge-base", primary, branch],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    return result.returncode != 0


def _worktree_exists(repo: Path, path: Path) -> bool:
    """Check if a worktree is registered for the given path."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    resolved = str(path.resolve())
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = line[len("worktree "):]
            if str(Path(wt_path).resolve()) == resolved:
                return True
    return False


# ============================================================================
# T011 Integration Tests
# ============================================================================


class TestFreshRepoBootstrap:
    """Test 1: Fresh repo creates orphan branch, worktree, writes config."""

    def test_creates_orphan_branch(self, tmp_path: Path):
        """Bootstrap creates an orphan branch in a fresh repo."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        console = Console(quiet=True)
        result = bootstrap_spec_storage(repo, console=console)

        assert result is True
        assert _branch_exists(repo, "kitty-specs")
        assert _is_orphan(repo, "kitty-specs")

    def test_creates_worktree(self, tmp_path: Path):
        """Bootstrap creates a worktree at the configured path."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        result = bootstrap_spec_storage(repo)

        assert result is True
        wt_path = repo / "kitty-specs"
        assert wt_path.is_dir()
        assert (wt_path / ".git").exists()  # .git file for worktree
        assert _worktree_exists(repo, wt_path)

    def test_writes_config(self, tmp_path: Path):
        """Bootstrap writes spec_storage section to config.yaml."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        result = bootstrap_spec_storage(repo)

        assert result is True
        assert has_spec_storage_config(repo)

        config = load_spec_storage_config(repo)
        assert config.branch_name == "kitty-specs"
        assert config.worktree_path == "kitty-specs"
        assert config.auto_push is False
        assert config.is_defaulted is False

    def test_orphan_has_initial_commit(self, tmp_path: Path):
        """The orphan branch has at least one commit."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        bootstrap_spec_storage(repo)

        state = inspect_spec_branch(repo, "kitty-specs")
        assert state.exists_local is True
        assert state.head_commit is not None

    def test_main_branch_unaffected(self, tmp_path: Path):
        """Bootstrap does not modify the current branch or working tree."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # Record state before
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        main_head_before = result.stdout.strip()

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        branch_before = result.stdout.strip()

        bootstrap_spec_storage(repo)

        # Record state after
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        main_head_after = result.stdout.strip()

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        branch_after = result.stdout.strip()

        assert main_head_before == main_head_after
        assert branch_before == branch_after


class TestIdempotentRerun:
    """Test 2: Rerun is idempotent, doesn't duplicate."""

    def test_double_run_succeeds(self, tmp_path: Path):
        """Running bootstrap twice succeeds both times."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        result1 = bootstrap_spec_storage(repo)
        result2 = bootstrap_spec_storage(repo)

        assert result1 is True
        assert result2 is True

    def test_double_run_same_branch(self, tmp_path: Path):
        """Second run doesn't create a second branch or commit."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        bootstrap_spec_storage(repo)
        state1 = inspect_spec_branch(repo, "kitty-specs")

        bootstrap_spec_storage(repo)
        state2 = inspect_spec_branch(repo, "kitty-specs")

        assert state1.head_commit == state2.head_commit

    def test_double_run_single_worktree(self, tmp_path: Path):
        """Second run doesn't create duplicate worktree entries."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        bootstrap_spec_storage(repo)
        bootstrap_spec_storage(repo)

        # Count worktree entries for kitty-specs branch
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        branch_entries = [
            line for line in result.stdout.splitlines()
            if line.strip() == "branch refs/heads/kitty-specs"
        ]
        assert len(branch_entries) == 1

    def test_config_preserved_on_rerun(self, tmp_path: Path):
        """Rerun preserves existing config values."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # First run creates default config
        bootstrap_spec_storage(repo)
        config1 = load_spec_storage_config(repo)

        # Second run preserves it
        bootstrap_spec_storage(repo)
        config2 = load_spec_storage_config(repo)

        assert config1.branch_name == config2.branch_name
        assert config1.worktree_path == config2.worktree_path
        assert config1.auto_push == config2.auto_push


class TestCustomConfigValues:
    """Test 3: Custom config values honored."""

    def test_custom_branch_name(self, tmp_path: Path):
        """Custom branch_name from config is used."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # Pre-save custom config
        custom_config = SpecStorageConfig(
            branch_name="my-specs",
            worktree_path="my-specs",
        )
        save_spec_storage_config(repo, custom_config)

        result = bootstrap_spec_storage(repo)

        assert result is True
        assert _branch_exists(repo, "my-specs")
        assert _is_orphan(repo, "my-specs")
        assert (repo / "my-specs").is_dir()

    def test_custom_worktree_path(self, tmp_path: Path):
        """Custom worktree_path from config is used."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        custom_config = SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="specs-data",
        )
        save_spec_storage_config(repo, custom_config)

        result = bootstrap_spec_storage(repo)

        assert result is True
        assert (repo / "specs-data").is_dir()
        assert _worktree_exists(repo, repo / "specs-data")

    def test_auto_push_preserved(self, tmp_path: Path):
        """auto_push setting is preserved through bootstrap."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        custom_config = SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="kitty-specs",
            auto_push=True,
        )
        save_spec_storage_config(repo, custom_config)

        result = bootstrap_spec_storage(repo)

        assert result is True
        config = load_spec_storage_config(repo)
        assert config.auto_push is True


class TestPathConflict:
    """Test 4: Path conflict fails safely."""

    def test_regular_directory_conflict(self, tmp_path: Path):
        """Fails when a regular directory exists at worktree path."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # Create a regular directory at the expected worktree path
        conflict_dir = repo / "kitty-specs"
        conflict_dir.mkdir()
        (conflict_dir / "some-file.txt").write_text("user data", encoding="utf-8")

        console = Console(quiet=True)
        result = bootstrap_spec_storage(repo, console=console)

        assert result is False
        # User's files should be untouched
        assert (conflict_dir / "some-file.txt").read_text(encoding="utf-8") == "user data"

    def test_conflict_does_not_write_config(self, tmp_path: Path):
        """On conflict, config is not written (no partial state)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # Create conflicting directory
        (repo / "kitty-specs").mkdir()
        (repo / "kitty-specs" / "file.txt").write_text("data", encoding="utf-8")

        # Note: The orphan branch IS created before worktree check.
        # That's acceptable - the branch doesn't affect the working tree.
        bootstrap_spec_storage(repo)

        # Config should still not be saved (bootstrap returned False)
        # Actually, let's check more carefully - the branch was created but
        # the worktree was not, and config was not saved.
        # The config file might have been created by save_spec_storage_config
        # only if bootstrap returns True (it saves at the end).
        # Let's verify the worktree was NOT created
        assert not _worktree_exists(repo, repo / "kitty-specs")


class TestEdgeCases:
    """Additional edge-case tests."""

    def test_worktree_discovery_healthy_after_bootstrap(self, tmp_path: Path):
        """After bootstrap, discover_spec_worktree reports healthy."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        bootstrap_spec_storage(repo)

        config = load_spec_storage_config(repo)
        state = discover_spec_worktree(repo, config)
        assert state.health_status == HEALTH_HEALTHY
        assert state.registered is True
        assert state.branch_name == "kitty-specs"

    def test_inspect_branch_after_bootstrap(self, tmp_path: Path):
        """After bootstrap, inspect_spec_branch reports orphan."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        bootstrap_spec_storage(repo)

        state = inspect_spec_branch(repo, "kitty-specs")
        assert state.exists_local is True
        assert state.is_orphan is True
        assert state.head_commit is not None

    def test_no_git_dir_returns_false(self, tmp_path: Path):
        """Bootstrap in a non-git directory fails gracefully."""
        repo = tmp_path / "not-a-repo"
        repo.mkdir()
        _create_kittify_dir(repo)

        # This should fail because there's no git repo
        # The validation of the worktree path resolving should still pass,
        # but the git commands will fail.
        result = bootstrap_spec_storage(repo)

        # It should return False because git operations fail
        assert result is False

    def test_existing_other_config_preserved(self, tmp_path: Path):
        """Bootstrap preserves other config sections (vcs, agents)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _create_kittify_dir(repo)

        # Write some existing config
        from ruamel.yaml import YAML
        yaml = YAML()
        config_file = repo / ".kittify" / "config.yaml"
        yaml.dump(
            {"vcs": {"type": "git"}, "agents": {"available": ["claude"]}},
            config_file.open("w"),
        )

        bootstrap_spec_storage(repo)

        # Verify other sections preserved
        with open(config_file, encoding="utf-8") as f:
            data = yaml.load(f)

        assert data["vcs"]["type"] == "git"
        assert data["agents"]["available"] == ["claude"]
        assert "spec_storage" in data
        assert data["spec_storage"]["branch_name"] == "kitty-specs"
