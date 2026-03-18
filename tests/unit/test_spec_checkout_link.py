"""Unit tests for parallel checkout spec symlink guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

from specify_cli.core.spec_checkout_link import ensure_parallel_checkout_specs_link


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_spec_storage_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")

    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    (repo / ".kittify").mkdir(parents=True, exist_ok=True)
    (repo / ".kittify" / "config.yaml").write_text(
        "spec_storage:\n"
        "  branch_name: kitty-specs\n"
        "  worktree_path: kitty-specs\n"
        "  auto_push: false\n",
        encoding="utf-8",
    )

    _git(repo, "add", "README.md", ".kittify/config.yaml")
    _git(repo, "commit", "-m", "Initial")

    _git(repo, "branch", "kitty-specs")
    _git(repo, "worktree", "add", str(repo / "kitty-specs"), "kitty-specs")
    return repo


def test_creates_symlink_in_parallel_checkout(tmp_path: Path) -> None:
    repo = _init_spec_storage_repo(tmp_path)
    parallel = tmp_path / "parallel"
    _git(repo, "worktree", "add", "-b", "parallel", str(parallel), "main")

    result = ensure_parallel_checkout_specs_link(parallel)
    link = parallel / "kitty-specs"

    assert result.status == "linked"
    assert link.is_symlink()
    assert link.resolve() == (repo / "kitty-specs").resolve()


def test_repairs_broken_symlink_in_parallel_checkout(tmp_path: Path) -> None:
    repo = _init_spec_storage_repo(tmp_path)
    parallel = tmp_path / "parallel"
    _git(repo, "worktree", "add", "-b", "parallel", str(parallel), "main")

    first = ensure_parallel_checkout_specs_link(parallel)
    assert first.status == "linked"

    link = parallel / "kitty-specs"
    link.unlink()
    link.symlink_to("missing-target", target_is_directory=True)

    repaired = ensure_parallel_checkout_specs_link(parallel)

    assert repaired.status == "repaired"
    assert link.is_symlink()
    assert link.resolve() == (repo / "kitty-specs").resolve()


def test_does_not_link_wp_workspace_checkouts(tmp_path: Path) -> None:
    repo = _init_spec_storage_repo(tmp_path)
    wp_checkout = repo / ".worktrees" / "001-feature-WP01"
    wp_checkout.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", "001-feature-WP01", str(wp_checkout), "main")

    result = ensure_parallel_checkout_specs_link(wp_checkout)

    assert result.status == "wp_workspace"
    assert not (wp_checkout / "kitty-specs").exists()


def test_does_not_overwrite_existing_directory(tmp_path: Path) -> None:
    repo = _init_spec_storage_repo(tmp_path)
    parallel = tmp_path / "parallel"
    _git(repo, "worktree", "add", "-b", "parallel", str(parallel), "main")

    local_specs = parallel / "kitty-specs"
    local_specs.mkdir(parents=True, exist_ok=True)
    (local_specs / "accidental.md").write_text("local", encoding="utf-8")

    result = ensure_parallel_checkout_specs_link(parallel)

    assert result.status == "conflict_existing_path"
    assert local_specs.is_dir()
    assert not local_specs.is_symlink()
