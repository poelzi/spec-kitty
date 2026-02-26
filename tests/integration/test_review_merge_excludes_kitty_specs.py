"""Integration tests for merge safety: spec path exclusion (WP06 / T028-T029).

Tests verify that the merge/integrate workflow prevents stale landing
branches from reintroducing ``kitty-specs/`` files into the upstream
branch (e.g., ``main``).

Discoverable via: ``pytest tests/integration -k "merge_excludes_kitty_specs"``

All tests use real temporary git repos (no git mocking).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_merge_safety import (
    filter_merge_paths,
    get_spec_path_exclusion_patterns,
    should_exclude_from_merge,
)


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


def _tracked_files(repo: Path, branch: str = "HEAD") -> list[str]:
    """Return list of tracked files on the given branch."""
    result = _git(
        ["ls-tree", "-r", "--name-only", branch],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]


def _create_stale_landing_branch(repo: Path) -> str:
    """Create a landing branch that still contains kitty-specs/ files.

    Simulates the scenario where a feature was developed before
    the spec branch migration, so the landing branch still has
    kitty-specs/ tracked on it.

    Returns the landing branch name.
    """
    landing_branch = "010-test-feature"

    # Create landing branch from main
    _git(["checkout", "-b", landing_branch], cwd=repo)

    # Add some implementation files (legitimate)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "feature.py").write_text(
        "# New feature implementation\n", encoding="utf-8"
    )

    # Add stale kitty-specs/ files (should NOT reach main)
    specs_dir = repo / "kitty-specs" / "010-test-feature" / "tasks"
    specs_dir.mkdir(parents=True)
    (repo / "kitty-specs" / "010-test-feature" / "spec.md").write_text(
        "# Spec\n", encoding="utf-8"
    )
    (repo / "kitty-specs" / "010-test-feature" / "plan.md").write_text(
        "# Plan\n", encoding="utf-8"
    )
    (specs_dir / "WP01-setup.md").write_text(
        "---\nwork_package_id: WP01\nlane: done\n---\n# WP01\n",
        encoding="utf-8",
    )

    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "feat(WP01): implement feature with stale specs"], cwd=repo)

    # Switch back to main
    _git(["checkout", "main"], cwd=repo)

    return landing_branch


def _create_landing_with_custom_spec_path(
    repo: Path, spec_path: str = ".my-specs"
) -> str:
    """Create a landing branch with custom spec path files."""
    landing_branch = "020-custom-specs"

    _git(["checkout", "-b", landing_branch], cwd=repo)

    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "custom.py").write_text("# Custom\n", encoding="utf-8")

    custom_specs = repo / spec_path / "020-custom-specs"
    custom_specs.mkdir(parents=True)
    (custom_specs / "spec.md").write_text("# Spec\n", encoding="utf-8")

    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "feat: custom spec path feature"], cwd=repo)

    _git(["checkout", "main"], cwd=repo)

    return landing_branch


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Create a clean git repo."""
    return _init_repo(tmp_path / "repo")


@pytest.fixture()
def stale_repo(repo: Path) -> tuple[Path, str]:
    """Repo with a stale landing branch containing kitty-specs/."""
    landing = _create_stale_landing_branch(repo)
    return repo, landing


# ============================================================================
# Test: Exclusion pattern generation in real repos
# ============================================================================


class TestExclusionPatternsIntegration:
    """Verify exclusion patterns work with real repo configs."""

    def test_default_patterns_without_config(self, repo: Path):
        """Repo without config falls back to kitty-specs patterns."""
        patterns = get_spec_path_exclusion_patterns(repo)
        assert "kitty-specs" in patterns
        assert "kitty-specs/*" in patterns

    def test_patterns_with_config(self, repo: Path):
        """Repo with spec_storage config uses configured path."""
        (repo / ".kittify").mkdir(exist_ok=True)
        (repo / ".kittify" / "config.yaml").write_text(
            "spec_storage:\n"
            "  branch_name: my-specs\n"
            "  worktree_path: .custom-specs\n"
            "  auto_push: false\n",
            encoding="utf-8",
        )
        patterns = get_spec_path_exclusion_patterns(repo)
        assert ".custom-specs" in patterns
        assert ".custom-specs/*" in patterns

    def test_exclusion_catches_stale_files(self, stale_repo):
        """Stale landing branch files are correctly identified for exclusion."""
        repo, landing = stale_repo
        patterns = get_spec_path_exclusion_patterns(repo)

        # Get files from landing branch
        result = _git(
            ["diff", "--name-only", f"main...{landing}"],
            cwd=repo,
        )
        changed_files = result.stdout.strip().splitlines()

        spec_files = [f for f in changed_files if should_exclude_from_merge(f, patterns)]
        non_spec_files = [f for f in changed_files if not should_exclude_from_merge(f, patterns)]

        # Spec files should be identified
        assert len(spec_files) > 0
        assert all("kitty-specs" in f for f in spec_files)

        # Implementation files should NOT be excluded
        assert "src/feature.py" in non_spec_files


# ============================================================================
# Test: Squash merge spec path exclusion
# ============================================================================


class TestSquashMergeExclusion:
    """Verify spec paths are excluded during squash merge flow."""

    def test_squash_merge_then_exclude_spec_files(self, stale_repo):
        """After squash merge, spec files can be removed from staging."""
        repo, landing = stale_repo

        # Squash merge the landing branch
        _git(["merge", "--squash", landing], cwd=repo)

        # Get staged files
        result = _git(["diff", "--cached", "--name-only"], cwd=repo)
        staged = result.stdout.strip().splitlines()

        # Verify spec files ARE in staging (before exclusion)
        spec_in_staging = [f for f in staged if "kitty-specs" in f]
        assert len(spec_in_staging) > 0

        # Apply exclusion: reset spec files from staging
        patterns = get_spec_path_exclusion_patterns(repo)
        for f in staged:
            if should_exclude_from_merge(f, patterns):
                _git(["reset", "HEAD", "--", f], cwd=repo, check=False)

        # Verify spec files are NO LONGER staged
        result = _git(["diff", "--cached", "--name-only"], cwd=repo)
        remaining = result.stdout.strip().splitlines()
        spec_remaining = [f for f in remaining if "kitty-specs" in f]
        assert spec_remaining == []

        # Implementation files should still be staged
        assert "src/feature.py" in remaining

    def test_squash_commit_without_spec_files(self, stale_repo):
        """Squash commit after exclusion does not contain spec files."""
        repo, landing = stale_repo

        # Squash merge
        _git(["merge", "--squash", landing], cwd=repo)

        # Exclude spec files
        patterns = get_spec_path_exclusion_patterns(repo)
        result = _git(["diff", "--cached", "--name-only"], cwd=repo)
        for f in result.stdout.strip().splitlines():
            if should_exclude_from_merge(f, patterns):
                _git(["reset", "HEAD", "--", f], cwd=repo, check=False)
                _git(["checkout", "HEAD", "--", f], cwd=repo, check=False)

        # Commit
        _git(["commit", "-m", "Integrate test feature"], cwd=repo)

        # Verify main does NOT have kitty-specs/
        tracked = _tracked_files(repo, "main")
        spec_tracked = [f for f in tracked if f.startswith("kitty-specs/")]
        assert spec_tracked == []

        # But implementation files ARE on main
        assert "src/feature.py" in tracked


# ============================================================================
# Test: Non-squash merge spec path exclusion
# ============================================================================


class TestNonSquashMergeExclusion:
    """Verify spec paths are removed after non-squash merge."""

    def test_merge_then_remove_spec_files(self, stale_repo):
        """After merge commit, spec files can be removed in a follow-up."""
        repo, landing = stale_repo

        # Merge (non-squash)
        _git(
            ["merge", "--no-ff", landing, "-m", "Merge test feature"],
            cwd=repo,
        )

        # Verify spec files ARE on main now (from merge)
        tracked = _tracked_files(repo, "main")
        spec_on_main = [f for f in tracked if f.startswith("kitty-specs/")]
        assert len(spec_on_main) > 0

        # Remove spec files in a follow-up commit
        patterns = get_spec_path_exclusion_patterns(repo)
        for f in spec_on_main:
            if should_exclude_from_merge(f, patterns):
                _git(["rm", "-f", "--", f], cwd=repo, check=False)

        _git(["commit", "-m", "chore: remove stale spec files"], cwd=repo)

        # Verify spec files are GONE from main
        tracked_after = _tracked_files(repo, "main")
        spec_after = [f for f in tracked_after if f.startswith("kitty-specs/")]
        assert spec_after == []

        # Implementation files still present
        assert "src/feature.py" in tracked_after


# ============================================================================
# Test: Non-spec files unaffected
# ============================================================================


class TestNonSpecFilesUnaffected:
    """Verify legitimate code changes are never excluded."""

    def test_implementation_files_pass_through(self, stale_repo):
        """filter_merge_paths preserves all non-spec files."""
        repo, landing = stale_repo

        result = _git(
            ["diff", "--name-only", f"main...{landing}"],
            cwd=repo,
        )
        all_files = result.stdout.strip().splitlines()
        patterns = get_spec_path_exclusion_patterns(repo)

        filtered = filter_merge_paths(all_files, patterns)

        # Implementation file must survive filtering
        assert "src/feature.py" in filtered

        # No spec files should survive
        assert not any("kitty-specs" in f for f in filtered)

    def test_root_files_not_excluded(self, repo: Path):
        """Root-level files like README.md, pyproject.toml are never excluded."""
        patterns = get_spec_path_exclusion_patterns(repo)
        root_files = ["README.md", "pyproject.toml", "src/main.py", ".gitignore"]
        filtered = filter_merge_paths(root_files, patterns)
        assert filtered == root_files


# ============================================================================
# Test: Custom worktree path
# ============================================================================


class TestCustomWorktreePathExclusion:
    """Verify exclusion works with custom worktree paths."""

    def test_custom_spec_path_exclusion(self, repo: Path):
        """Custom worktree_path files are correctly excluded."""
        # Commit config to main so it's available on disk after checkout.
        (repo / ".kittify").mkdir(exist_ok=True)
        (repo / ".kittify" / "config.yaml").write_text(
            "spec_storage:\n"
            "  branch_name: my-specs\n"
            "  worktree_path: .my-specs\n"
            "  auto_push: false\n",
            encoding="utf-8",
        )
        _git(["add", "."], cwd=repo)
        _git(["commit", "-m", "chore: add spec storage config"], cwd=repo)

        landing = _create_landing_with_custom_spec_path(repo, ".my-specs")
        patterns = get_spec_path_exclusion_patterns(repo)

        # Get diff
        result = _git(
            ["diff", "--name-only", f"main...{landing}"],
            cwd=repo,
        )
        all_files = result.stdout.strip().splitlines()
        filtered = filter_merge_paths(all_files, patterns)

        # Custom spec files should be excluded
        assert not any(".my-specs" in f for f in filtered)

        # Implementation files should remain
        assert "src/custom.py" in filtered
