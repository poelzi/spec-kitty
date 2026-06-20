"""Integration tests for worktree-aware commit routing.

Verifies that when ``kitty-specs/`` is a git worktree (separate branch),
spec-kitty commits WP lane/status changes to the kitty-specs worktree
instead of the main repository.  This prevents unrelated merge conflicts
in the main repo from blocking spec-kitty operations.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from specify_cli.core.spec_commit_guard import (
    SpecCommitContext,
    resolve_specs_repo_and_branch,
)
from specify_cli.core.spec_storage_config import (
    SpecStorageConfig,
    save_spec_storage_config,
)
from specify_cli.git.commit_helpers import safe_commit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(repo: Path) -> None:
    """Create a git repo with an initial commit on ``main``."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "Initial commit")


def _setup_kitty_specs_worktree(repo: Path) -> Path:
    """Create a ``kitty-specs`` branch and add it as a worktree.

    Returns the worktree path.
    """
    _run_git(repo, "branch", "kitty-specs")
    wt_path = repo / "kitty-specs"
    _run_git(repo, "worktree", "add", str(wt_path), "kitty-specs")
    return wt_path


def _create_wp_file(
    kitty_specs_dir: Path,
    feature_slug: str,
    wp_id: str = "WP01",
    lane: str = "planned",
) -> Path:
    """Create a minimal WP file under kitty-specs and commit it."""
    tasks_dir = kitty_specs_dir / feature_slug / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    wp_file = tasks_dir / f"{wp_id}-setup.md"
    wp_file.write_text(
        f"---\n"
        f'work_package_id: {wp_id}\n'
        f'title: Setup\n'
        f'dependencies: []\n'
        f'lane: "{lane}"\n'
        f'agent: ""\n'
        f'shell_pid: ""\n'
        f"---\n"
        f"# {wp_id} Setup\n\n"
        f"## Activity Log\n"
        f"- 2026-01-01T00:00:00Z - system - lane={lane} - Prompt created.\n",
        encoding="utf-8",
    )
    return wp_file


def _create_meta_json(
    kitty_specs_dir: Path,
    feature_slug: str,
    upstream_branch: str = "main",
) -> Path:
    """Create a meta.json for the feature."""
    feature_dir = kitty_specs_dir / feature_slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    meta_file = feature_dir / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "feature_number": "001",
                "slug": feature_slug,
                "upstream_branch": upstream_branch,
                "target_branch": feature_slug,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return meta_file


def _current_branch(repo: Path) -> str:
    return _run_git(repo, "branch", "--show-current").stdout.strip()


def _last_commit_message(repo: Path) -> str:
    return _run_git(repo, "log", "-1", "--format=%s").stdout.strip()


def _commit_count(repo: Path) -> int:
    result = _run_git(repo, "rev-list", "--count", "HEAD")
    return int(result.stdout.strip())


# ---------------------------------------------------------------------------
# Tests for resolve_specs_repo_and_branch
# ---------------------------------------------------------------------------


class TestResolveSpecsRepoAndBranch:
    """Unit tests for the unified worktree detection helper."""

    def test_detects_kitty_specs_worktree(self, tmp_path: Path) -> None:
        """When kitty-specs/ is a git worktree, detect it."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        _setup_kitty_specs_worktree(repo)

        context = resolve_specs_repo_and_branch(repo, "001-test-feature")

        assert context.commit_repo_root == (repo / "kitty-specs").resolve()
        assert context.target_branch == "kitty-specs"
        assert context.branch_source == "worktree_detected"

    def test_falls_back_to_meta_json_without_worktree(self, tmp_path: Path) -> None:
        """When kitty-specs/ is a regular dir, use meta.json branch."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        _create_meta_json(repo / "kitty-specs", "001-test-feature", upstream_branch="develop")

        context = resolve_specs_repo_and_branch(repo, "001-test-feature")

        assert context.commit_repo_root == repo
        assert context.target_branch == "develop"
        assert context.branch_source == "feature_meta"

    def test_falls_back_to_current_branch(self, tmp_path: Path) -> None:
        """Without worktree or meta.json, use current branch."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        (repo / "kitty-specs").mkdir()

        context = resolve_specs_repo_and_branch(repo)

        assert context.commit_repo_root == repo.resolve()
        assert context.target_branch == "main"
        assert context.branch_source == "current_branch"

    def test_worktree_takes_precedence_over_meta_json(self, tmp_path: Path) -> None:
        """Worktree detection overrides meta.json upstream_branch."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        # meta.json says "main" but worktree is on "kitty-specs"
        _create_meta_json(wt_path, "001-test-feature", upstream_branch="main")

        context = resolve_specs_repo_and_branch(repo, "001-test-feature")

        assert context.commit_repo_root == wt_path.resolve()
        assert context.target_branch == "kitty-specs"
        assert context.branch_source == "worktree_detected"

    def test_no_kitty_specs_dir_falls_back(self, tmp_path: Path) -> None:
        """When kitty-specs/ doesn't exist at all, fall back gracefully."""
        repo = tmp_path / "repo"
        _init_repo(repo)

        context = resolve_specs_repo_and_branch(repo)

        assert context.commit_repo_root == repo.resolve()
        assert context.target_branch == "main"
        assert context.branch_source == "current_branch"


# ---------------------------------------------------------------------------
# Tests for safe_commit routing with worktrees
# ---------------------------------------------------------------------------


class TestSafeCommitWorktreeRouting:
    """Verify safe_commit lands commits in the correct repo."""

    def test_commit_lands_in_kitty_specs_worktree(self, tmp_path: Path) -> None:
        """safe_commit with worktree repo_path commits there, not main."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        # Create a WP file in the worktree
        wp_file = _create_wp_file(wt_path, "001-test-feature")
        _run_git(wt_path, "add", ".")
        _run_git(wt_path, "commit", "-m", "Add WP01")

        # Modify the file
        wp_file.write_text(
            wp_file.read_text(encoding="utf-8").replace('"planned"', '"doing"'),
            encoding="utf-8",
        )

        main_commits_before = _commit_count(repo)
        wt_commits_before = _commit_count(wt_path)

        # Commit via safe_commit targeting the worktree
        success = safe_commit(
            repo_path=wt_path,
            files_to_commit=[wp_file.resolve()],
            commit_message="chore: Move WP01 to doing",
            no_verify=True,
        )

        assert success
        # Worktree got a new commit
        assert _commit_count(wt_path) == wt_commits_before + 1
        assert _last_commit_message(wt_path) == "chore: Move WP01 to doing"
        # Main repo did NOT get a new commit
        assert _commit_count(repo) == main_commits_before

    def test_main_repo_conflict_does_not_block_worktree_commit(
        self, tmp_path: Path
    ) -> None:
        """Unresolved merge conflict in main repo must not prevent
        commits to the kitty-specs worktree."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        # Create a conflict in the main repo
        conflict_file = repo / "conflict.txt"
        conflict_file.write_text("line 1\n", encoding="utf-8")
        _run_git(repo, "add", "conflict.txt")
        _run_git(repo, "commit", "-m", "Add conflict file")

        _run_git(repo, "checkout", "-b", "conflict-branch")
        conflict_file.write_text("line 1 from branch\n", encoding="utf-8")
        _run_git(repo, "add", "conflict.txt")
        _run_git(repo, "commit", "-m", "Branch change")

        _run_git(repo, "checkout", "main")
        conflict_file.write_text("line 1 from main\n", encoding="utf-8")
        _run_git(repo, "add", "conflict.txt")
        _run_git(repo, "commit", "-m", "Main change")

        # Trigger merge conflict
        merge_result = subprocess.run(
            ["git", "merge", "conflict-branch"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert merge_result.returncode != 0, "Expected merge conflict"

        # Verify main repo is in conflict state
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert "UU" in status.stdout or "AA" in status.stdout, (
            f"Expected unmerged files, got: {status.stdout}"
        )

        # Now create and modify a WP file in the worktree
        wp_file = _create_wp_file(wt_path, "001-test-feature")
        _run_git(wt_path, "add", ".")
        _run_git(wt_path, "commit", "-m", "Add WP01")

        wp_file.write_text(
            wp_file.read_text(encoding="utf-8").replace('"planned"', '"doing"'),
            encoding="utf-8",
        )

        # Resolve the specs repo — should point to worktree, not main
        context = resolve_specs_repo_and_branch(repo, "001-test-feature")
        assert context.branch_source == "worktree_detected"

        # Commit to the worktree — should succeed despite main repo conflict
        success = safe_commit(
            repo_path=context.commit_repo_root,
            files_to_commit=[wp_file.resolve()],
            commit_message="chore: Move WP01 to doing",
            no_verify=True,
        )

        assert success, (
            "safe_commit to kitty-specs worktree should succeed "
            "even when main repo has merge conflicts"
        )
        assert _last_commit_message(wt_path) == "chore: Move WP01 to doing"


# ---------------------------------------------------------------------------
# Tests for prepare_specs_commit_context with worktrees
# ---------------------------------------------------------------------------


class TestPrepareSpecsCommitContextWorktree:
    """Verify prepare_specs_commit_context handles worktrees correctly."""

    def test_routes_to_worktree_without_spec_storage(self, tmp_path: Path) -> None:
        """Even without spec_storage config, worktree detection works."""
        from specify_cli.core.spec_commit_guard import prepare_specs_commit_context

        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        feature_dir = wt_path / "001-test-feature"
        feature_dir.mkdir(parents=True)
        _create_meta_json(wt_path, "001-test-feature", upstream_branch="main")
        wp_file = _create_wp_file(wt_path, "001-test-feature")

        context = prepare_specs_commit_context(
            repo,
            tracked_paths=[wp_file],
            feature_dir=feature_dir,
        )

        assert context.commit_repo_root == wt_path.resolve()
        assert context.target_branch == "kitty-specs"
        assert context.branch_source == "worktree_detected"

    def test_non_worktree_preserves_existing_behaviour(self, tmp_path: Path) -> None:
        """Regular kitty-specs/ subdirectory still uses meta.json branch."""
        from specify_cli.core.spec_commit_guard import prepare_specs_commit_context

        repo = tmp_path / "repo"
        _init_repo(repo)

        feature_dir = repo / "kitty-specs" / "001-test-feature"
        feature_dir.mkdir(parents=True)
        _create_meta_json(
            repo / "kitty-specs", "001-test-feature", upstream_branch="develop"
        )
        wp_file = _create_wp_file(repo / "kitty-specs", "001-test-feature")

        context = prepare_specs_commit_context(
            repo,
            tracked_paths=[wp_file],
            feature_dir=feature_dir,
        )

        assert context.commit_repo_root == repo.resolve()
        assert context.target_branch == "develop"
        assert context.branch_source == "feature_meta"


# ---------------------------------------------------------------------------
# End-to-end workflow tests
# ---------------------------------------------------------------------------


class TestWorkflowImplementWorktreeCommitRouting:
    """Verify workflow implement commits to worktree when detected."""

    def test_implement_commits_to_kitty_specs_worktree(self, tmp_path: Path) -> None:
        """workflow implement should commit status to kitty-specs worktree."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        feature_slug = "001-test-feature"
        _create_meta_json(wt_path, feature_slug)
        wp_file = _create_wp_file(wt_path, feature_slug, lane="planned")
        _run_git(wt_path, "add", ".")
        _run_git(wt_path, "commit", "-m", "Add WP01")

        # Create workspace directory (implement expects it)
        workspace_path = repo / ".worktrees" / f"{feature_slug}-WP01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        main_commits_before = _commit_count(repo)

        from specify_cli.cli.commands.agent.workflow import implement as agent_implement

        with patch(
            "specify_cli.cli.commands.agent.workflow.locate_project_root",
            return_value=repo,
        ), patch(
            "specify_cli.cli.commands.agent.workflow._find_feature_slug",
            return_value=feature_slug,
        ):
            try:
                agent_implement(
                    wp_id="WP01",
                    feature=feature_slug,
                    agent="test-agent",
                    base=None,
                )
            except (SystemExit, typer.Exit):
                pass  # CLI exits after printing prompt

        # Main repo should NOT have gained commits
        assert _commit_count(repo) == main_commits_before

        # Worktree should have the status commit
        last_msg = _last_commit_message(wt_path)
        assert "WP01" in last_msg
        assert "test-agent" in last_msg

    def test_implement_reattaches_detached_spec_storage_despite_dirty_main(
        self, tmp_path: Path
    ) -> None:
        """Detached spec-storage worktree is reattached before status commit."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        wt_path = _setup_kitty_specs_worktree(repo)

        save_spec_storage_config(
            repo,
            SpecStorageConfig(
                branch_name="kitty-specs",
                worktree_path="kitty-specs",
                auto_push=False,
            ),
        )
        _run_git(repo, "add", ".kittify/config.yaml")
        _run_git(repo, "commit", "-m", "Add spec storage config")

        feature_slug = "001-test-feature"
        _create_meta_json(wt_path, feature_slug)
        _create_wp_file(wt_path, feature_slug, lane="planned")
        _run_git(wt_path, "add", ".")
        _run_git(wt_path, "commit", "-m", "Add WP01")
        _run_git(wt_path, "checkout", "--detach")

        dirty_file = repo / "dirty-main.txt"
        dirty_file.write_text("main worktree dirt\n", encoding="utf-8")

        workspace_path = repo / ".worktrees" / f"{feature_slug}-WP01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        from specify_cli.cli.commands.agent.workflow import implement as agent_implement

        with patch(
            "specify_cli.cli.commands.agent.workflow.locate_project_root",
            return_value=repo,
        ), patch(
            "specify_cli.cli.commands.agent.workflow._find_feature_slug",
            return_value=feature_slug,
        ):
            try:
                agent_implement(
                    wp_id="WP01",
                    feature=feature_slug,
                    agent="test-agent",
                    base=None,
                )
            except (SystemExit, typer.Exit):
                pass

        assert _current_branch(repo) == "main"
        assert _current_branch(wt_path) == "kitty-specs"
        assert "test-agent" in _last_commit_message(wt_path)

        status = _run_git(repo, "status", "--porcelain").stdout
        assert "?? dirty-main.txt" in status


# ---------------------------------------------------------------------------
# Patch 1 — kitty_specs_lock serialisation
# ---------------------------------------------------------------------------


class TestKittySpecsLock:
    """The advisory lock must serialise concurrent kitty-specs writers."""

    def test_lock_serialises_concurrent_acquire_release(self, tmp_path: Path) -> None:
        """Two threads holding the lock cannot overlap; release lets the
        second proceed."""
        import threading
        import time

        from specify_cli.core.spec_lock import kitty_specs_lock

        repo = tmp_path / "repo"
        _init_repo(repo)

        # Track which thread is in the critical section over time.
        in_section: list[str] = []
        first_acquired = threading.Event()
        first_release_allowed = threading.Event()

        def thread_a() -> None:
            with kitty_specs_lock(repo):
                in_section.append("A_in")
                first_acquired.set()
                # Hold the lock until the test allows release.
                first_release_allowed.wait(timeout=5.0)
                in_section.append("A_out")

        def thread_b() -> None:
            # Wait until A is inside the critical section, then try to
            # acquire.  We expect to block until A releases.
            first_acquired.wait(timeout=5.0)
            in_section.append("B_attempt")
            with kitty_specs_lock(repo):
                in_section.append("B_in")
                in_section.append("B_out")

        t_a = threading.Thread(target=thread_a)
        t_b = threading.Thread(target=thread_b)
        t_a.start()
        t_b.start()

        # Give B a moment to attempt and block.
        time.sleep(0.2)
        # Let A release; B should then proceed.
        first_release_allowed.set()

        t_a.join(timeout=5.0)
        t_b.join(timeout=5.0)
        assert not t_a.is_alive() and not t_b.is_alive()

        # A's critical section must be contiguous (no B_in between A_in/A_out).
        a_in = in_section.index("A_in")
        a_out = in_section.index("A_out")
        try:
            b_in = in_section.index("B_in")
        except ValueError:  # pragma: no cover - sanity
            pytest.fail(f"B never entered the critical section: {in_section}")
        assert a_in < a_out < b_in, (
            f"Lock failed to serialise critical sections: {in_section}"
        )

    def test_lock_times_out_when_held(self, tmp_path: Path) -> None:
        """When another holder owns the lock, a short timeout raises."""
        import threading

        from specify_cli.core.spec_lock import LockTimeoutError, kitty_specs_lock

        repo = tmp_path / "repo"
        _init_repo(repo)

        held = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with kitty_specs_lock(repo):
                held.set()
                release.wait(timeout=5.0)

        t = threading.Thread(target=holder)
        t.start()
        try:
            assert held.wait(timeout=2.0)
            with pytest.raises(LockTimeoutError):
                # 0.5s timeout — should give up promptly.
                with kitty_specs_lock(repo, timeout_s=0.5):
                    pytest.fail("lock should not have been acquired")
        finally:
            release.set()
            t.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Patch 2 — safe_commit HEAD verification
# ---------------------------------------------------------------------------


class TestSafeCommitHeadVerification:
    """``safe_commit`` must refuse to commit on the wrong branch / parent."""

    def test_rejects_when_expected_branch_differs_from_head(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        # Initial HEAD is on ``main``; ask safe_commit to refuse if we're
        # not on a fake other branch.
        target_file = repo / "note.txt"
        target_file.write_text("hi", encoding="utf-8")

        ok = safe_commit(
            repo_path=repo,
            files_to_commit=[target_file],
            commit_message="should not commit",
            expected_branch="some-other-branch",
        )
        assert ok is False
        # Nothing should have been committed.
        assert _last_commit_message(repo) == "Initial commit"

    def test_rejects_when_concurrent_commit_changes_parent_oid(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        captured_parent = _run_git(repo, "rev-parse", "HEAD").stdout.strip()
        # Simulate a concurrent commit between resolve and our commit.
        (repo / "concurrent.txt").write_text("from other process", encoding="utf-8")
        _run_git(repo, "add", "concurrent.txt")
        _run_git(repo, "commit", "-m", "concurrent commit from another process")

        target_file = repo / "note.txt"
        target_file.write_text("hi", encoding="utf-8")
        ok = safe_commit(
            repo_path=repo,
            files_to_commit=[target_file],
            commit_message="should report concurrent modification",
            expected_branch="main",
            expected_parent_oid=captured_parent,
        )
        # The commit was made (cannot atomically un-commit) but the helper
        # returns False so the caller knows another process raced.
        assert ok is False
        # Two commits since "Initial commit": the concurrent one and ours.
        assert _commit_count(repo) == 3


# ---------------------------------------------------------------------------
# Patch 3 — detached worktree branch precedence
# ---------------------------------------------------------------------------


class TestDetachedWorktreePrecedence:
    """``_detached_worktree_context`` must prefer config over the dirname."""

    def test_prefers_spec_storage_config_over_dirname(self, tmp_path: Path) -> None:
        from specify_cli.core.spec_commit_guard import _detached_worktree_context

        repo = tmp_path / "repo"
        _init_repo(repo)
        # Create TWO branches that both exist in the same .git store: the
        # dirname guess (``kitty-specs``) and the config-named branch
        # (``orphan-specs``).
        _run_git(repo, "branch", "kitty-specs")
        _run_git(repo, "branch", "orphan-specs")
        wt_path = repo / "kitty-specs"
        _run_git(repo, "worktree", "add", "--detach", str(wt_path), "kitty-specs")

        # Write a spec_storage config pointing at the orphan-specs branch.
        save_spec_storage_config(
            repo,
            SpecStorageConfig(branch_name="orphan-specs", worktree_path="kitty-specs"),
        )

        ctx = _detached_worktree_context(wt_path.resolve(), main_repo_root=repo)
        assert ctx is not None
        assert ctx.target_branch == "orphan-specs"
        assert ctx.branch_source == "worktree_detached"

    def test_falls_back_to_dirname_with_guess_marker(self, tmp_path: Path) -> None:
        from specify_cli.core.spec_commit_guard import _detached_worktree_context

        repo = tmp_path / "repo"
        _init_repo(repo)
        # Only the dirname-matching branch exists; no spec_storage config.
        _run_git(repo, "branch", "kitty-specs")
        wt_path = repo / "kitty-specs"
        _run_git(repo, "worktree", "add", "--detach", str(wt_path), "kitty-specs")

        ctx = _detached_worktree_context(wt_path.resolve(), main_repo_root=repo)
        assert ctx is not None
        assert ctx.target_branch == "kitty-specs"
        # The new "_guess" marker flags this as a heuristic, not confirmed.
        assert ctx.branch_source == "worktree_detached_guess"


# ---------------------------------------------------------------------------
# Patch 4 — content-equivalence skip in _auto_rebase_worktree_if_needed
# ---------------------------------------------------------------------------


class TestAutoRebaseContentEquivalenceSkip:
    """A WP worktree whose tree matches landing must NOT trigger a rebase."""

    def test_skips_rebase_when_tree_matches_landing_at_different_sha(
        self, tmp_path: Path
    ) -> None:
        from specify_cli.cli.commands.agent.tasks import _auto_rebase_worktree_if_needed

        repo = tmp_path / "repo"
        _init_repo(repo)
        feature_slug = "049-fixture"
        wp_id = "WP01"

        # Wire enough kitty-specs scaffolding for the WP-mission check + the
        # base-branch lookup.
        kitty_specs = repo / "kitty-specs"
        kitty_specs.mkdir()
        feature_dir = kitty_specs / feature_slug
        feature_dir.mkdir()
        (feature_dir / "meta.json").write_text(
            json.dumps(
                {
                    "feature_number": "049",
                    "slug": feature_slug,
                    "mission": "software-dev",
                    "upstream_branch": "main",
                    "target_branch": feature_slug,
                }
            ),
            encoding="utf-8",
        )

        # Create the "landing" feature branch (named after the feature slug)
        # with a unique commit so it diverges from main by SHA.
        _run_git(repo, "checkout", "-b", feature_slug)
        (repo / "shared.txt").write_text("landed content\n", encoding="utf-8")
        _run_git(repo, "add", "shared.txt")
        _run_git(repo, "commit", "-m", "landing commit on feature branch")
        landing_sha = _run_git(repo, "rev-parse", "HEAD").stdout.strip()

        # Create the WP worktree at a DIFFERENT commit whose TREE matches
        # landing.  Use checkout -b + commit --amend to get a divergent SHA.
        _run_git(repo, "checkout", "main")
        wt_path = repo / ".worktrees" / f"{feature_slug}-{wp_id}"
        wt_path.parent.mkdir(exist_ok=True)
        _run_git(
            repo, "worktree", "add", "-b", f"{feature_slug}-{wp_id}", str(wt_path), "main"
        )
        (wt_path / "shared.txt").write_text("landed content\n", encoding="utf-8")
        _run_git(wt_path, "add", "shared.txt")
        _run_git(wt_path, "commit", "-m", "wp commit that lands the same tree")
        wp_sha = _run_git(wt_path, "rev-parse", "HEAD").stdout.strip()
        assert wp_sha != landing_sha
        # Sanity: the trees ARE equal.
        diff_quiet = subprocess.run(
            ["git", "diff", "--quiet", f"HEAD..{feature_slug}"],
            cwd=wt_path,
            check=False,
        )
        assert diff_quiet.returncode == 0

        # The auto-rebase helper must short-circuit because the trees match.
        is_valid, guidance, rebased = _auto_rebase_worktree_if_needed(
            wt_path, feature_slug, wp_id
        )
        assert is_valid is True
        assert rebased is False
        assert guidance == []

        # Confirm no actual rebase happened (SHA unchanged).
        post_sha = _run_git(wt_path, "rev-parse", "HEAD").stdout.strip()
        assert post_sha == wp_sha
