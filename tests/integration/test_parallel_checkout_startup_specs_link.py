"""Integration test for startup symlink guard in parallel checkouts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _run_cli(project_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    from tests.test_isolation_helpers import get_venv_python

    env = os.environ.copy()
    src_path = REPO_ROOT / "src"
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(
        os.pathsep
    )
    env.setdefault("SPEC_KITTY_TEMPLATE_ROOT", str(REPO_ROOT))
    command = [str(get_venv_python()), "-m", "specify_cli.__init__", *args]
    return subprocess.run(
        command,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        env=env,
    )


def test_startup_creates_specs_symlink_in_parallel_checkout(tmp_path: Path) -> None:
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

    parallel = tmp_path / "parallel"
    _git(repo, "worktree", "add", "-b", "parallel", str(parallel), "main")

    result = _run_cli(parallel, "repair", "worktree", "--all")
    assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    link = parallel / "kitty-specs"
    assert link.is_symlink()
    assert link.resolve() == (repo / "kitty-specs").resolve()
