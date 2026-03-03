"""Integration tests for mark-status fallback to WP files."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(project_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Execute spec-kitty CLI using Python module invocation."""
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


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def test_mark_status_updates_wp_files_and_commits_in_specs_submodule(tmp_path: Path) -> None:
    """mark-status should work when tasks.md is absent and kitty-specs is nested."""
    repo = tmp_path / "repo"
    specs_origin = tmp_path / "specs-origin"
    _init_repo(repo)
    _init_repo(specs_origin)

    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(specs_origin),
            "kitty-specs",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "commit", "-m", "Add specs submodule"], cwd=repo, check=True, capture_output=True)

    kittify = repo / ".kittify"
    kittify.mkdir(exist_ok=True)
    (kittify / "config.yaml").write_text(
        "vcs:\n"
        "  type: git\n"
        "agents:\n"
        "  available:\n"
        "    - claude\n",
        encoding="utf-8",
    )
    (kittify / "metadata.yaml").write_text(
        "spec_kitty:\n"
        "  version: 0.16.0\n",
        encoding="utf-8",
    )

    specs_repo = repo / "kitty-specs"
    subprocess.run(["git", "config", "user.name", "Test"], cwd=specs_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=specs_repo, check=True, capture_output=True)

    feature_dir = specs_repo / "001-submodule-feature"
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    (feature_dir / "meta.json").write_text(
        json.dumps(
            {
                "feature_number": "001",
                "slug": "001-submodule-feature",
                "upstream_branch": "main",
                "target_branch": "main",
                "vcs": "git",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    wp_file = tasks_dir / "WP01-subtask.md"
    wp_file.write_text(
        "---\n"
        "work_package_id: WP01\n"
        "lane: planned\n"
        "---\n\n"
        "# WP01\n\n"
        "## Subtasks\n"
        "- [ ] T001 Initial setup\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=specs_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add feature WP file"], cwd=specs_repo, check=True, capture_output=True)

    main_head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    specs_head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=specs_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_cli(
        repo,
        "agent",
        "tasks",
        "mark-status",
        "T001",
        "--status",
        "done",
        "--feature",
        "001-submodule-feature",
        "--json",
    )
    assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    output = json.loads(result.stdout)
    assert output["result"] == "success"
    assert output["updated"] == ["T001"]
    assert any(path.endswith("WP01-subtask.md") for path in output["files_updated"])

    wp_content = wp_file.read_text(encoding="utf-8")
    assert "- [x] T001 Initial setup" in wp_content

    specs_head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=specs_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    main_head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert specs_head_after != specs_head_before
    assert main_head_after == main_head_before


def test_mark_status_updates_tasks_md_in_specs_submodule_without_pathspec_warning(
    tmp_path: Path,
) -> None:
    """mark-status should stage tasks.md inside nested kitty-specs repo."""
    repo = tmp_path / "repo"
    specs_origin = tmp_path / "specs-origin"
    _init_repo(repo)
    _init_repo(specs_origin)

    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(specs_origin),
            "kitty-specs",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "commit", "-m", "Add specs submodule"], cwd=repo, check=True, capture_output=True)

    kittify = repo / ".kittify"
    kittify.mkdir(exist_ok=True)
    (kittify / "config.yaml").write_text(
        "vcs:\n"
        "  type: git\n"
        "agents:\n"
        "  available:\n"
        "    - claude\n",
        encoding="utf-8",
    )
    (kittify / "metadata.yaml").write_text(
        "spec_kitty:\n"
        "  version: 0.16.0\n",
        encoding="utf-8",
    )

    specs_repo = repo / "kitty-specs"
    subprocess.run(["git", "config", "user.name", "Test"], cwd=specs_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=specs_repo, check=True, capture_output=True)

    feature_dir = specs_repo / "001-submodule-feature"
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    (feature_dir / "meta.json").write_text(
        json.dumps(
            {
                "feature_number": "001",
                "slug": "001-submodule-feature",
                "upstream_branch": "main",
                "target_branch": "main",
                "vcs": "git",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    tasks_md = feature_dir / "tasks.md"
    tasks_md.write_text(
        "# Tasks\n\n"
        "## WP02\n\n"
        "- [ ] T007 do thing\n"
        "- [ ] T008 do thing\n"
        "- [ ] T009 do thing\n"
        "- [ ] T010 do thing\n"
        "- [ ] T011 do thing\n"
        "- [ ] T012 do thing\n",
        encoding="utf-8",
    )

    (tasks_dir / "WP02-test.md").write_text(
        "---\n"
        "work_package_id: WP02\n"
        "lane: planned\n"
        "---\n\n"
        "# WP02\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=specs_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add feature tasks"], cwd=specs_repo, check=True, capture_output=True)

    main_head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    specs_head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=specs_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = run_cli(
        repo,
        "agent",
        "tasks",
        "mark-status",
        "T007",
        "T008",
        "T009",
        "T010",
        "T011",
        "T012",
        "--status",
        "done",
        "--feature",
        "001-submodule-feature",
    )
    assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
    assert "Failed to stage file" not in result.stdout
    assert "Pathspec" not in result.stdout
    assert "Failed to stage file" not in result.stderr
    assert "Pathspec" not in result.stderr

    tasks_md_content = tasks_md.read_text(encoding="utf-8")
    for task_id in ["T007", "T008", "T009", "T010", "T011", "T012"]:
        assert f"- [x] {task_id}" in tasks_md_content

    specs_head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=specs_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    main_head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert specs_head_after != specs_head_before
    assert main_head_after == main_head_before
