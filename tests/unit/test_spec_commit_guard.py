"""Unit tests for guarded spec commit context resolution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specify_cli.core.spec_commit_guard import prepare_specs_commit_context
from specify_cli.core.spec_storage_config import SpecStorageConfig, save_spec_storage_config


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "Initial")


def _current_branch(repo: Path) -> str:
    return _run_git(repo, "branch", "--show-current").stdout.strip()


def test_prepare_context_uses_feature_metadata_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    feature_dir = repo / "kitty-specs" / "001-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "meta.json").write_text(
        json.dumps({"upstream_branch": "develop"}, indent=2) + "\n",
        encoding="utf-8",
    )
    tasks_md = feature_dir / "tasks.md"
    tasks_md.write_text("# Tasks\n", encoding="utf-8")

    context = prepare_specs_commit_context(
        repo,
        tracked_paths=[tasks_md],
        feature_dir=feature_dir,
    )

    assert context.commit_repo_root == repo.resolve()
    assert context.target_branch == "develop"
    assert context.branch_source == "feature_meta"
    assert _current_branch(repo) == "develop"


def test_prepare_context_uses_spec_storage_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    _run_git(repo, "checkout", "-b", "kitty-specs")
    _run_git(repo, "checkout", "main")
    _run_git(repo, "worktree", "add", str(repo / "kitty-specs"), "kitty-specs")

    save_spec_storage_config(
        repo,
        SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="kitty-specs",
            auto_push=False,
        ),
    )

    feature_dir = repo / "kitty-specs" / "001-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "meta.json").write_text(
        json.dumps({"upstream_branch": "main"}, indent=2) + "\n",
        encoding="utf-8",
    )
    tasks_md = feature_dir / "tasks.md"
    tasks_md.write_text("# Tasks\n", encoding="utf-8")

    context = prepare_specs_commit_context(
        repo,
        tracked_paths=[tasks_md],
        feature_dir=feature_dir,
        fallback_branch="main",
    )

    expected_repo = (repo / "kitty-specs").resolve()
    assert context.commit_repo_root == expected_repo
    assert context.target_branch == "kitty-specs"
    assert context.branch_source == "spec_storage"
    assert _current_branch(expected_repo) == "kitty-specs"


def test_prepare_context_errors_when_spec_storage_branch_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    save_spec_storage_config(
        repo,
        SpecStorageConfig(
            branch_name="kitty-specs",
            worktree_path="kitty-specs",
            auto_push=False,
        ),
    )

    feature_dir = repo / "kitty-specs" / "001-test-feature"
    feature_dir.mkdir(parents=True)
    tasks_md = feature_dir / "tasks.md"
    tasks_md.write_text("# Tasks\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Spec storage branch 'kitty-specs' not found"):
        prepare_specs_commit_context(
            repo,
            tracked_paths=[tasks_md],
            feature_dir=feature_dir,
        )
