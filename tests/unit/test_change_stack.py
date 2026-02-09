"""Unit tests for change stack routing, validation, and policy enforcement.

Tests cover:
- T007: Stash resolver (main vs feature branch routing)
- T010: Ambiguity fail-fast detection
- T011: Closed/done link-only policy enforcement
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from specify_cli.core.change_stack import (
    AmbiguityResult,
    BranchStash,
    ChangeStackError,
    ClosedReferenceCheck,
    StashScope,
    ValidationState,
    _extract_feature_slug,
    check_ambiguity,
    check_closed_references,
    resolve_stash,
    validate_change_request,
    validate_no_closed_mutation,
)


# ============================================================================
# T007: Stash Resolver Tests
# ============================================================================


class TestResolveStash:
    """Test branch stash routing logic."""

    def test_main_branch_routes_to_main_stash(self, tmp_path: Path) -> None:
        """main branch should route to kitty-specs/change-stack/main/."""
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="main"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="main")

        assert stash.stash_key == "main"
        assert stash.scope == StashScope.MAIN
        assert stash.stash_path == tmp_path / "kitty-specs" / "change-stack" / "main"

    def test_master_branch_routes_to_main_stash(self, tmp_path: Path) -> None:
        """master branch should also route to main stash."""
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="master"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="master")

        assert stash.stash_key == "main"
        assert stash.scope == StashScope.MAIN

    def test_feature_branch_routes_to_feature_stash(self, tmp_path: Path) -> None:
        """Feature branch should route to kitty-specs/<feature>/tasks/."""
        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="029-mid-stream-change")

        assert stash.stash_key == "029-mid-stream-change"
        assert stash.scope == StashScope.FEATURE
        assert stash.stash_path == tmp_path / "kitty-specs" / "029-mid-stream-change" / "tasks"

    def test_worktree_branch_routes_to_feature_stash(self, tmp_path: Path) -> None:
        """Worktree branch (###-feature-WP##) should strip WP suffix."""
        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="029-mid-stream-change-WP01")

        assert stash.stash_key == "029-mid-stream-change"
        assert stash.scope == StashScope.FEATURE

    def test_unrecognized_branch_raises_error(self, tmp_path: Path) -> None:
        """Branches that don't match any pattern should raise ChangeStackError."""
        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            with pytest.raises(ChangeStackError, match="Cannot resolve stash"):
                resolve_stash(tmp_path, branch="some-random-branch")

    def test_auto_detect_branch(self, tmp_path: Path) -> None:
        """When branch is None, should auto-detect from git."""
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="main"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path)

        assert stash.stash_key == "main"

    def test_no_branch_detected_raises_error(self, tmp_path: Path) -> None:
        """Should raise error if git branch cannot be determined."""
        with patch("specify_cli.core.change_stack.get_current_branch", return_value=None), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            with pytest.raises(ChangeStackError, match="Could not determine"):
                resolve_stash(tmp_path)

    def test_main_stash_tasks_doc_when_exists(self, tmp_path: Path) -> None:
        """Should include tasks_doc_path if tasks.md exists."""
        stash_dir = tmp_path / "kitty-specs" / "change-stack" / "main"
        stash_dir.mkdir(parents=True)
        tasks_doc = stash_dir / "tasks.md"
        tasks_doc.write_text("# Tasks", encoding="utf-8")

        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="main")

        assert stash.tasks_doc_path == tasks_doc

    def test_feature_stash_tasks_doc_when_missing(self, tmp_path: Path) -> None:
        """Should have None tasks_doc_path when tasks.md doesn't exist."""
        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            stash = resolve_stash(tmp_path, branch="029-test-feature")

        assert stash.tasks_doc_path is None


class TestExtractFeatureSlug:
    """Test feature slug extraction from branch names."""

    def test_direct_feature_branch(self) -> None:
        assert _extract_feature_slug("029-mid-stream-change") == "029-mid-stream-change"

    def test_worktree_branch(self) -> None:
        assert _extract_feature_slug("029-mid-stream-change-WP01") == "029-mid-stream-change"

    def test_worktree_branch_double_digit(self) -> None:
        assert _extract_feature_slug("001-demo-WP12") == "001-demo"

    def test_non_feature_branch(self) -> None:
        assert _extract_feature_slug("develop") is None

    def test_main_branch(self) -> None:
        assert _extract_feature_slug("main") is None

    def test_release_branch(self) -> None:
        assert _extract_feature_slug("release-v1.0") is None

    def test_three_digit_prefix_only(self) -> None:
        """Branch must have content after the number prefix."""
        assert _extract_feature_slug("029-a") == "029-a"

    def test_hyphenated_feature_name(self) -> None:
        assert _extract_feature_slug("001-my-complex-feature-name") == "001-my-complex-feature-name"


# ============================================================================
# T010: Ambiguity Detection Tests
# ============================================================================


class TestCheckAmbiguity:
    """Test ambiguity fail-fast gate."""

    def test_empty_request_is_ambiguous(self) -> None:
        result = check_ambiguity("")
        assert result.is_ambiguous
        assert "empty request" in result.matched_patterns

    def test_whitespace_only_is_ambiguous(self) -> None:
        result = check_ambiguity("   ")
        assert result.is_ambiguous

    def test_this_block_is_ambiguous(self) -> None:
        result = check_ambiguity("change this block to use async")
        assert result.is_ambiguous
        assert any("this block" in p for p in result.matched_patterns)

    def test_that_section_is_ambiguous(self) -> None:
        result = check_ambiguity("rewrite that section")
        assert result.is_ambiguous

    def test_clear_request_is_not_ambiguous(self) -> None:
        result = check_ambiguity("use SQLAlchemy instead of raw SQL queries")
        assert not result.is_ambiguous

    def test_file_reference_disambiguates(self) -> None:
        """File references should disambiguate vague language."""
        result = check_ambiguity("change this block in change_stack.py")
        assert not result.is_ambiguous

    def test_wp_reference_disambiguates(self) -> None:
        """WP references should disambiguate."""
        result = check_ambiguity("change this block in WP01")
        assert not result.is_ambiguous

    def test_function_reference_disambiguates(self) -> None:
        """Function/class references should disambiguate."""
        result = check_ambiguity("change this block in function resolve_stash")
        assert not result.is_ambiguous

    def test_quoted_identifier_disambiguates(self) -> None:
        """Quoted identifiers should disambiguate."""
        result = check_ambiguity('change this block in "my_function"')
        assert not result.is_ambiguous

    def test_specific_request_is_valid(self) -> None:
        result = check_ambiguity("replace manual JSON parsing with pydantic models in data_model.py")
        assert not result.is_ambiguous

    def test_ambiguity_provides_clarification_prompt(self) -> None:
        result = check_ambiguity("fix this part")
        assert result.is_ambiguous
        assert result.clarification_prompt is not None
        assert "clarify" in result.clarification_prompt.lower()

    def test_here_is_ambiguous(self) -> None:
        result = check_ambiguity("add validation here")
        assert result.is_ambiguous

    def test_directive_with_target_is_valid(self) -> None:
        """FR-002: Directive phrasing like 'use this library instead' should work."""
        result = check_ambiguity("use SQLAlchemy instead of raw SQL")
        assert not result.is_ambiguous

    def test_revert_with_file_is_valid(self) -> None:
        result = check_ambiguity("revert changes to config.yaml")
        assert not result.is_ambiguous

    def test_do_not_remove_with_target_is_valid(self) -> None:
        result = check_ambiguity("do not remove the `validate_input` function")
        assert not result.is_ambiguous


# ============================================================================
# T011: Closed/Done Policy Tests
# ============================================================================


class TestCheckClosedReferences:
    """Test closed/done WP reference detection."""

    def test_no_wp_references(self, tmp_path: Path) -> None:
        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            result = check_closed_references("add caching layer", tmp_path, "001-demo")
        assert not result.has_closed_references
        assert result.closed_wp_ids == []

    def test_reference_to_open_wp(self, tmp_path: Path) -> None:
        """Open WPs should not be flagged."""
        tasks_dir = tmp_path / "kitty-specs" / "001-demo" / "tasks"
        tasks_dir.mkdir(parents=True)
        wp_file = tasks_dir / "WP01-setup.md"
        wp_file.write_text('---\nlane: "doing"\n---\n# Setup', encoding="utf-8")

        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            result = check_closed_references("modify WP01 approach", tmp_path, "001-demo")
        assert not result.has_closed_references

    def test_reference_to_done_wp(self, tmp_path: Path) -> None:
        """Done WPs should be flagged as closed references."""
        tasks_dir = tmp_path / "kitty-specs" / "001-demo" / "tasks"
        tasks_dir.mkdir(parents=True)
        wp_file = tasks_dir / "WP01-setup.md"
        wp_file.write_text('---\nlane: "done"\n---\n# Setup', encoding="utf-8")

        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            result = check_closed_references("like WP01 but with caching", tmp_path, "001-demo")
        assert result.has_closed_references
        assert "WP01" in result.closed_wp_ids
        assert result.linkable  # Always linkable, never reopenable

    def test_multiple_references_mixed(self, tmp_path: Path) -> None:
        """Should only flag done WPs, not open ones."""
        tasks_dir = tmp_path / "kitty-specs" / "001-demo" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "WP01-setup.md").write_text('---\nlane: "done"\n---\n', encoding="utf-8")
        (tasks_dir / "WP02-core.md").write_text('---\nlane: "doing"\n---\n', encoding="utf-8")

        with patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            result = check_closed_references(
                "apply WP01 pattern to WP02", tmp_path, "001-demo"
            )
        assert result.has_closed_references
        assert "WP01" in result.closed_wp_ids
        assert "WP02" not in result.closed_wp_ids


class TestValidateNoClosedMutation:
    """Test that closed WPs cannot be mutated."""

    def test_no_closed_wps(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "WP01-setup.md").write_text('---\nlane: "doing"\n---\n', encoding="utf-8")

        blocked = validate_no_closed_mutation(["WP01"], tasks_dir)
        assert blocked == []

    def test_closed_wp_blocked(self, tmp_path: Path) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "WP01-setup.md").write_text('---\nlane: "done"\n---\n', encoding="utf-8")

        blocked = validate_no_closed_mutation(["WP01"], tasks_dir)
        assert blocked == ["WP01"]

    def test_missing_wp_not_blocked(self, tmp_path: Path) -> None:
        """Non-existent WPs should not be blocked."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        blocked = validate_no_closed_mutation(["WP99"], tasks_dir)
        assert blocked == []


# ============================================================================
# Integration: validate_change_request
# ============================================================================


class TestValidateChangeRequest:
    """Test the combined validation pipeline."""

    def test_valid_request_on_feature_branch(self, tmp_path: Path) -> None:
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            req = validate_change_request(
                "use pydantic models in data_model.py",
                tmp_path,
                branch="029-test",
            )

        assert req.validation_state == ValidationState.VALID
        assert req.stash.scope == StashScope.FEATURE
        assert req.stash.stash_key == "029-test"
        assert not req.ambiguity.is_ambiguous

    def test_ambiguous_request_fails_fast(self, tmp_path: Path) -> None:
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="029-test"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            req = validate_change_request(
                "change this block",
                tmp_path,
                branch="029-test",
            )

        assert req.validation_state == ValidationState.AMBIGUOUS
        assert req.ambiguity.is_ambiguous

    def test_main_branch_routing(self, tmp_path: Path) -> None:
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="main"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            req = validate_change_request(
                "add retry logic to API calls",
                tmp_path,
                branch="main",
            )

        assert req.stash.scope == StashScope.MAIN
        assert req.stash.stash_key == "main"

    def test_request_id_generated(self, tmp_path: Path) -> None:
        with patch("specify_cli.core.change_stack.get_current_branch", return_value="main"), \
             patch("specify_cli.core.change_stack._get_main_repo_root", return_value=tmp_path):
            req = validate_change_request("add caching", tmp_path, branch="main")

        assert req.request_id
        assert len(req.request_id) == 8  # UUID prefix
