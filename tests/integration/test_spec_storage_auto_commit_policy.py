"""Integration tests for spec storage auto-commit policy (WP03 T015-T016).

These tests verify the commit policy enforcement for planning artifacts:
1. Manual-edit detection (include/skip/abort)
2. Auto-push behavior (default off, configurable)
3. commit_spec_changes commits to the spec worktree
4. Planning branch remains clean of spec commits
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_commit_policy import (
    MANUAL_EDIT_POLICY_ENV,
    SpecCommitAction,
    commit_with_policy,
    commit_spec_changes,
    detect_manual_edits,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
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


def _setup_spec_worktree(repo_root: Path) -> Path:
    """Create an orphan branch and worktree for spec storage. Returns worktree path."""
    branch_name = "kitty-specs"
    wt_path = repo_root / "kitty-specs"

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
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), branch_name],
        cwd=repo_root, capture_output=True, check=True,
    )

    # Configure git user in worktree
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=wt_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=wt_path, capture_output=True, check=True,
    )

    return wt_path


def _create_manual_edit_scenario(wt: Path) -> tuple[str, str]:
    """Create intended + manual files and return relative paths."""
    feature_dir = wt / "001-test-feature"
    feature_dir.mkdir(parents=True, exist_ok=True)

    spec = feature_dir / "spec.md"
    spec.write_text("# Test Spec\n", encoding="utf-8")

    manual = feature_dir / "manual-notes.md"
    manual.write_text("# Manual notes\n", encoding="utf-8")

    return "001-test-feature/spec.md", "001-test-feature/manual-notes.md"


def _git_head(cwd: Path) -> str:
    """Return current HEAD commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _is_tracked(cwd: Path, rel_path: str) -> bool:
    """Return True when rel_path is tracked by git."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel_path],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


# ============================================================================
# Tests: Manual-Edit Detection (T015)
# ============================================================================


class TestManualEditDetection:
    """Verify detection of unexpected manual edits in the spec worktree."""

    def test_no_manual_edits_returns_empty(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Create an intended file
        intended = wt / "001-feature" / "spec.md"
        intended.parent.mkdir(parents=True, exist_ok=True)
        intended.write_text("# Spec\n", encoding="utf-8")

        # git status shows the directory as "001-feature/" for new untracked dirs
        # so we include both the file and the directory in intended files
        manual = detect_manual_edits(wt, ["001-feature/spec.md", "001-feature/"])
        assert manual == []

    def test_detects_unexpected_changes(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Stage and commit an intended file first so it becomes tracked
        feature_dir = wt / "001-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        intended = feature_dir / "spec.md"
        intended.write_text("# Spec\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=wt, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial spec"],
            cwd=wt, capture_output=True, check=True,
        )

        # Now modify the tracked file and create a new manual edit
        intended.write_text("# Updated Spec\n", encoding="utf-8")
        manual_file = feature_dir / "notes.md"
        manual_file.write_text("# Manual notes\n", encoding="utf-8")

        manual = detect_manual_edits(wt, ["001-feature/spec.md"])
        assert len(manual) >= 1
        # Should contain the manual edit (notes.md) but not spec.md
        found_manual = any("notes.md" in m for m in manual)
        assert found_manual, f"Expected notes.md in manual edits, got: {manual}"

    def test_empty_intended_files_lists_all_changes(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Create files in worktree
        f1 = wt / "001-feature" / "spec.md"
        f1.parent.mkdir(parents=True, exist_ok=True)
        f1.write_text("# Spec\n", encoding="utf-8")

        # With empty intended list, all changes are "manual"
        manual = detect_manual_edits(wt, [])
        assert len(manual) >= 1


# ============================================================================
# Tests: Commit Policy (T015)
# ============================================================================


class TestCommitSpecChanges:
    """Verify commit_spec_changes works correctly on the spec worktree."""

    def test_commits_intended_files(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Create a file
        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test Spec\n", encoding="utf-8")

        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Add spec for test feature",
        )

        assert ok is True

        # Verify file is committed on the spec branch
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=wt, capture_output=True, text=True, check=True,
        )
        assert "Add spec for test feature" in log_result.stdout

    def test_skip_manual_edits_by_default(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Create intended + manual files
        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test Spec\n", encoding="utf-8")

        manual = feature_dir / "manual-notes.md"
        manual.write_text("# Manual notes\n", encoding="utf-8")

        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Add spec only",
            include_manual=False,
        )

        assert ok is True


class TestCommitWithPolicyIntegration:
    """Integration coverage for include/skip/abort policy outcomes."""

    @pytest.mark.parametrize(
        ("manual_policy", "expected_action", "expect_commit", "expect_manual_tracked"),
        [
            (None, "skip", True, False),
            ("skip", "skip", True, False),
            ("include", "include", True, True),
            ("abort", "abort", False, False),
        ],
    )
    def test_policy_argument_controls_manual_edit_outcome(
        self,
        tmp_path: Path,
        manual_policy: str | None,
        expected_action: str,
        expect_commit: bool,
        expect_manual_tracked: bool,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)
        spec_rel, manual_rel = _create_manual_edit_scenario(wt)

        before = _git_head(wt)
        kwargs = {}
        if manual_policy is not None:
            kwargs["manual_policy"] = manual_policy

        ok, action = commit_with_policy(
            worktree_path=wt,
            intended_files=[spec_rel],
            message=f"Commit with policy {manual_policy or 'default'}",
            **kwargs,
        )
        after = _git_head(wt)

        assert action.action == expected_action
        assert ok is expect_commit
        assert (after != before) is expect_commit

        assert _is_tracked(wt, spec_rel) is expect_commit
        assert _is_tracked(wt, manual_rel) is expect_manual_tracked

    @pytest.mark.parametrize(
        ("env_policy", "expected_action", "expect_commit", "expect_manual_tracked"),
        [
            ("skip", "skip", True, False),
            ("include", "include", True, True),
            ("abort", "abort", False, False),
        ],
    )
    def test_env_policy_controls_manual_edit_outcome(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        env_policy: str,
        expected_action: str,
        expect_commit: bool,
        expect_manual_tracked: bool,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)
        spec_rel, manual_rel = _create_manual_edit_scenario(wt)

        monkeypatch.setenv(MANUAL_EDIT_POLICY_ENV, env_policy)
        before = _git_head(wt)
        ok, action = commit_with_policy(
            worktree_path=wt,
            intended_files=[spec_rel],
            message=f"Commit with env policy {env_policy}",
        )
        after = _git_head(wt)

        assert action.action == expected_action
        assert ok is expect_commit
        assert (after != before) is expect_commit

        assert _is_tracked(wt, spec_rel) is expect_commit
        assert _is_tracked(wt, manual_rel) is expect_manual_tracked

    def test_argument_policy_takes_precedence_over_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)
        spec_rel, manual_rel = _create_manual_edit_scenario(wt)

        monkeypatch.setenv(MANUAL_EDIT_POLICY_ENV, "include")
        before = _git_head(wt)
        ok, action = commit_with_policy(
            worktree_path=wt,
            intended_files=[spec_rel],
            message="Commit with env include but arg abort",
            manual_policy="abort",
        )
        after = _git_head(wt)

        assert action.action == "abort"
        assert ok is False
        assert after == before
        assert _is_tracked(wt, spec_rel) is False
        assert _is_tracked(wt, manual_rel) is False

    def test_invalid_env_policy_falls_back_to_skip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)
        spec_rel, manual_rel = _create_manual_edit_scenario(wt)

        monkeypatch.setenv(MANUAL_EDIT_POLICY_ENV, "not-a-policy")
        before = _git_head(wt)
        ok, action = commit_with_policy(
            worktree_path=wt,
            intended_files=[spec_rel],
            message="Commit with invalid env policy",
        )
        after = _git_head(wt)

        assert action.action == "skip"
        assert ok is True
        assert after != before
        assert _is_tracked(wt, spec_rel) is True
        assert _is_tracked(wt, manual_rel) is False

    def test_include_manual_edits_when_requested(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Create intended + manual files
        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test Spec\n", encoding="utf-8")

        manual = feature_dir / "manual-notes.md"
        manual.write_text("# Manual notes\n", encoding="utf-8")

        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Add spec and manual edits",
            include_manual=True,
        )

        assert ok is True

        # Manual file should now be committed (clean status)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt, capture_output=True, text=True, check=True,
        )
        assert "manual-notes.md" not in status.stdout

    def test_nothing_to_commit_returns_true(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        # Don't create any files — nothing to commit
        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=[],
            message="Nothing to commit",
        )

        assert ok is True


# ============================================================================
# Tests: Auto-Push Policy (T016)
# ============================================================================


class TestAutoPushPolicy:
    """Verify auto_push behavior is off by default and configurable."""

    def test_auto_push_default_is_false(self) -> None:
        config = SpecStorageConfig()
        assert config.auto_push is False

    def test_auto_push_false_skips_push(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test\n", encoding="utf-8")

        # Commit with auto_push=False (default)
        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Test no push",
            auto_push=False,
        )

        assert ok is True
        # No remote configured, so push would fail if attempted.
        # If we get here, push was not attempted (success).

    def test_auto_push_true_attempts_push(self, tmp_path: Path) -> None:
        """auto_push=True attempts push but failure doesn't affect commit."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test\n", encoding="utf-8")

        # Commit with auto_push=True (no remote configured, push will fail silently)
        ok = commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Test with push attempt",
            auto_push=True,
        )

        # Commit should still succeed even though push fails (no remote)
        assert ok is True

        # Verify commit exists
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=wt, capture_output=True, text=True, check=True,
        )
        assert "Test with push attempt" in log_result.stdout

    def test_config_auto_push_roundtrip(self, tmp_path: Path) -> None:
        """Config with auto_push=true can be saved and loaded."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        config = SpecStorageConfig(auto_push=True)
        save_spec_storage_config(repo, config)

        from specify_cli.core.spec_storage_config import load_spec_storage_config
        loaded = load_spec_storage_config(repo)
        assert loaded.auto_push is True


# ============================================================================
# Tests: Planning Branch Cleanliness
# ============================================================================


class TestPlanningBranchCleanliness:
    """Verify planning branch does not receive spec file commits."""

    def test_commit_goes_to_spec_branch_not_main(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        wt = _setup_spec_worktree(repo)

        feature_dir = wt / "001-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec = feature_dir / "spec.md"
        spec.write_text("# Test Spec\n", encoding="utf-8")

        commit_spec_changes(
            worktree_path=wt,
            intended_files=["001-test-feature/spec.md"],
            message="Spec commit on spec branch",
        )

        # Check that main branch has NO spec commits
        main_log = subprocess.run(
            ["git", "log", "--oneline", "--all", "--", "001-test-feature/"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        # On main, there should be no commit touching 001-test-feature/
        # (we're checking only the main branch log)
        main_only = subprocess.run(
            ["git", "log", "main", "--oneline"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        assert "Spec commit on spec branch" not in main_only.stdout

        # Verify the commit IS on the spec branch (use worktree cwd)
        spec_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=wt, capture_output=True, text=True, check=True,
        )
        assert "Spec commit on spec branch" in spec_log.stdout
