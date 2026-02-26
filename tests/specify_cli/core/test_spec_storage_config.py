"""Unit tests for spec_storage config schema, accessors, and validation.

Tests cover:
- T001: Config schema defaults (SpecStorageConfig dataclass)
- T002: Config read/write accessors (load, save, has, get_abs_path)
- T003: Config validation (branch name, worktree path, auto_push)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specify_cli.core.spec_storage_config import (
    DEFAULT_AUTO_PUSH,
    DEFAULT_BRANCH_NAME,
    DEFAULT_WORKTREE_PATH,
    SpecStorageConfig,
    SpecStorageConfigError,
    get_spec_worktree_abs_path,
    has_spec_storage_config,
    load_spec_storage_config,
    save_spec_storage_config,
    validate_spec_storage_config,
    validate_spec_storage_raw,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Create a minimal repo root with .kittify/ directory."""
    kittify = tmp_path / ".kittify"
    kittify.mkdir()
    return tmp_path


@pytest.fixture
def repo_with_config(repo_root: Path) -> Path:
    """Create a repo root with a config.yaml containing spec_storage."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "vcs:\n"
        "  type: git\n"
        "agents:\n"
        "  available:\n"
        "    - claude\n"
        "spec_storage:\n"
        "  branch_name: my-specs\n"
        "  worktree_path: my-specs\n"
        "  auto_push: true\n",
        encoding="utf-8",
    )
    return repo_root


@pytest.fixture
def repo_with_legacy_config(repo_root: Path) -> Path:
    """Create a repo root with config.yaml but no spec_storage block."""
    config_file = repo_root / ".kittify" / "config.yaml"
    config_file.write_text(
        "vcs:\n"
        "  type: git\n"
        "agents:\n"
        "  available:\n"
        "    - claude\n",
        encoding="utf-8",
    )
    return repo_root


# ============================================================================
# T001 - Config Schema Defaults
# ============================================================================


class TestSpecStorageConfigDefaults:
    """Test SpecStorageConfig dataclass defaults."""

    def test_default_values(self):
        """Default constructor produces correct defaults."""
        cfg = SpecStorageConfig()
        assert cfg.branch_name == DEFAULT_BRANCH_NAME
        assert cfg.worktree_path == DEFAULT_WORKTREE_PATH
        assert cfg.auto_push == DEFAULT_AUTO_PUSH
        assert cfg.is_defaulted is False

    def test_default_constants(self):
        """Module-level constants have expected values."""
        assert DEFAULT_BRANCH_NAME == "kitty-specs"
        assert DEFAULT_WORKTREE_PATH == "kitty-specs"
        assert DEFAULT_AUTO_PUSH is False

    def test_custom_values(self):
        """Custom values override defaults."""
        cfg = SpecStorageConfig(
            branch_name="custom-specs",
            worktree_path="specs",
            auto_push=True,
        )
        assert cfg.branch_name == "custom-specs"
        assert cfg.worktree_path == "specs"
        assert cfg.auto_push is True

    def test_is_defaulted_flag(self):
        """is_defaulted tracks whether values came from config file."""
        defaulted = SpecStorageConfig(is_defaulted=True)
        assert defaulted.is_defaulted is True

        explicit = SpecStorageConfig(is_defaulted=False)
        assert explicit.is_defaulted is False


# ============================================================================
# T002 - Config Read/Write Accessors
# ============================================================================


class TestHasSpecStorageConfig:
    """Test has_spec_storage_config()."""

    def test_returns_true_when_present(self, repo_with_config: Path):
        """Returns True when spec_storage block exists."""
        assert has_spec_storage_config(repo_with_config) is True

    def test_returns_false_for_legacy(self, repo_with_legacy_config: Path):
        """Returns False when spec_storage is absent (legacy layout)."""
        assert has_spec_storage_config(repo_with_legacy_config) is False

    def test_returns_false_no_config_file(self, tmp_path: Path):
        """Returns False when config file does not exist."""
        assert has_spec_storage_config(tmp_path) is False

    def test_returns_false_empty_config(self, repo_root: Path):
        """Returns False for an empty config.yaml."""
        (repo_root / ".kittify" / "config.yaml").write_text("", encoding="utf-8")
        assert has_spec_storage_config(repo_root) is False


class TestLoadSpecStorageConfig:
    """Test load_spec_storage_config()."""

    def test_load_explicit_values(self, repo_with_config: Path):
        """Loads explicit values from config file."""
        cfg = load_spec_storage_config(repo_with_config)
        assert cfg.branch_name == "my-specs"
        assert cfg.worktree_path == "my-specs"
        assert cfg.auto_push is True
        assert cfg.is_defaulted is False

    def test_load_missing_config_returns_defaults(self, tmp_path: Path):
        """Missing config file returns defaults with is_defaulted=True."""
        cfg = load_spec_storage_config(tmp_path)
        assert cfg.branch_name == DEFAULT_BRANCH_NAME
        assert cfg.worktree_path == DEFAULT_WORKTREE_PATH
        assert cfg.auto_push is False
        assert cfg.is_defaulted is True

    def test_load_legacy_config_returns_defaults(
        self, repo_with_legacy_config: Path
    ):
        """Config without spec_storage section returns defaults."""
        cfg = load_spec_storage_config(repo_with_legacy_config)
        assert cfg.branch_name == DEFAULT_BRANCH_NAME
        assert cfg.auto_push is False
        assert cfg.is_defaulted is True

    def test_load_partial_config_fills_defaults(self, repo_root: Path):
        """Partial spec_storage block fills missing keys with defaults."""
        config_file = repo_root / ".kittify" / "config.yaml"
        config_file.write_text(
            "spec_storage:\n"
            "  branch_name: custom-branch\n",
            encoding="utf-8",
        )
        cfg = load_spec_storage_config(repo_root)
        assert cfg.branch_name == "custom-branch"
        assert cfg.worktree_path == DEFAULT_WORKTREE_PATH  # defaulted
        assert cfg.auto_push is False  # defaulted
        assert cfg.is_defaulted is False

    def test_load_invalid_yaml_raises(self, repo_root: Path):
        """Invalid YAML raises SpecStorageConfigError."""
        config_file = repo_root / ".kittify" / "config.yaml"
        config_file.write_text("invalid: yaml: : :\n  [bad", encoding="utf-8")
        with pytest.raises(SpecStorageConfigError, match="Invalid YAML"):
            load_spec_storage_config(repo_root)

    def test_load_spec_storage_not_dict_raises(self, repo_root: Path):
        """spec_storage as non-dict raises SpecStorageConfigError."""
        config_file = repo_root / ".kittify" / "config.yaml"
        config_file.write_text(
            "spec_storage: just-a-string\n", encoding="utf-8"
        )
        with pytest.raises(SpecStorageConfigError, match="must be a mapping"):
            load_spec_storage_config(repo_root)


class TestSaveSpecStorageConfig:
    """Test save_spec_storage_config()."""

    def test_save_creates_new_section(self, repo_with_legacy_config: Path):
        """Saving adds spec_storage without disturbing other sections."""
        cfg = SpecStorageConfig(
            branch_name="my-branch",
            worktree_path="my-wt",
            auto_push=True,
        )
        save_spec_storage_config(repo_with_legacy_config, cfg)

        # Reload and verify
        loaded = load_spec_storage_config(repo_with_legacy_config)
        assert loaded.branch_name == "my-branch"
        assert loaded.worktree_path == "my-wt"
        assert loaded.auto_push is True

        # Verify other sections preserved
        config_file = repo_with_legacy_config / ".kittify" / "config.yaml"
        content = config_file.read_text(encoding="utf-8")
        assert "vcs:" in content
        assert "agents:" in content

    def test_save_overwrites_existing(self, repo_with_config: Path):
        """Saving updates existing spec_storage values."""
        cfg = SpecStorageConfig(branch_name="new-branch")
        save_spec_storage_config(repo_with_config, cfg)

        loaded = load_spec_storage_config(repo_with_config)
        assert loaded.branch_name == "new-branch"

    def test_save_creates_directory_if_missing(self, tmp_path: Path):
        """Saving creates .kittify directory if needed."""
        cfg = SpecStorageConfig()
        save_spec_storage_config(tmp_path, cfg)

        assert (tmp_path / ".kittify" / "config.yaml").exists()
        loaded = load_spec_storage_config(tmp_path)
        assert loaded.branch_name == DEFAULT_BRANCH_NAME

    def test_roundtrip_preserves_values(self, repo_root: Path):
        """Save then load preserves all values."""
        original = SpecStorageConfig(
            branch_name="specs",
            worktree_path="spec-dir",
            auto_push=True,
        )
        save_spec_storage_config(repo_root, original)
        loaded = load_spec_storage_config(repo_root)

        assert loaded.branch_name == original.branch_name
        assert loaded.worktree_path == original.worktree_path
        assert loaded.auto_push == original.auto_push


class TestGetSpecWorktreeAbsPath:
    """Test get_spec_worktree_abs_path()."""

    def test_default_path(self, repo_root: Path):
        """Default config produces repo_root/kitty-specs."""
        cfg = SpecStorageConfig()
        result = get_spec_worktree_abs_path(repo_root, cfg)
        assert result == (repo_root / "kitty-specs").resolve()

    def test_custom_path(self, repo_root: Path):
        """Custom worktree_path is resolved correctly."""
        cfg = SpecStorageConfig(worktree_path="specs/planning")
        result = get_spec_worktree_abs_path(repo_root, cfg)
        assert result == (repo_root / "specs" / "planning").resolve()

    def test_auto_loads_config(self, repo_with_config: Path):
        """Loads config automatically when none provided."""
        result = get_spec_worktree_abs_path(repo_with_config)
        assert result == (repo_with_config / "my-specs").resolve()

    def test_result_is_absolute(self, repo_root: Path):
        """Result is always an absolute path."""
        cfg = SpecStorageConfig(worktree_path="relative/path")
        result = get_spec_worktree_abs_path(repo_root, cfg)
        assert result.is_absolute()


# ============================================================================
# T003 - Config Validation
# ============================================================================


class TestValidateSpecStorageConfig:
    """Test validate_spec_storage_config()."""

    def test_valid_defaults(self, repo_root: Path):
        """Default config passes validation."""
        cfg = SpecStorageConfig()
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    def test_valid_custom(self, repo_root: Path):
        """Custom but valid config passes validation."""
        cfg = SpecStorageConfig(
            branch_name="feature/specs",
            worktree_path="specs",
            auto_push=True,
        )
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    # --- branch_name validation ---

    def test_invalid_branch_with_spaces(self, repo_root: Path):
        """Branch name with spaces fails."""
        cfg = SpecStorageConfig(branch_name="my branch")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]
        assert "spaces" in errors[0]

    def test_invalid_branch_double_dots(self, repo_root: Path):
        """Branch name with .. fails."""
        cfg = SpecStorageConfig(branch_name="bad..branch")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_starts_with_dash(self, repo_root: Path):
        """Branch name starting with - fails."""
        cfg = SpecStorageConfig(branch_name="-bad")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_starts_with_dot(self, repo_root: Path):
        """Branch name starting with . fails."""
        cfg = SpecStorageConfig(branch_name=".bad")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_ends_with_lock(self, repo_root: Path):
        """Branch name ending with .lock fails."""
        cfg = SpecStorageConfig(branch_name="name.lock")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]
        assert ".lock" in errors[0]

    def test_invalid_branch_ends_with_dot(self, repo_root: Path):
        """Branch name ending with . fails."""
        cfg = SpecStorageConfig(branch_name="name.")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_empty(self, repo_root: Path):
        """Empty branch name fails."""
        cfg = SpecStorageConfig(branch_name="")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]
        assert "empty" in errors[0]

    def test_invalid_branch_tilde(self, repo_root: Path):
        """Branch name with ~ fails."""
        cfg = SpecStorageConfig(branch_name="bad~name")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_caret(self, repo_root: Path):
        """Branch name with ^ fails."""
        cfg = SpecStorageConfig(branch_name="bad^name")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_invalid_branch_colon(self, repo_root: Path):
        """Branch name with : fails."""
        cfg = SpecStorageConfig(branch_name="bad:name")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.branch_name" in errors[0]

    def test_valid_branch_with_slashes(self, repo_root: Path):
        """Branch name with slashes is valid (refs/heads style)."""
        cfg = SpecStorageConfig(branch_name="feature/specs")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    def test_valid_branch_with_hyphens(self, repo_root: Path):
        """Branch name with hyphens is valid."""
        cfg = SpecStorageConfig(branch_name="my-specs-branch")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    # --- worktree_path validation ---

    def test_worktree_path_escapes_root(self, repo_root: Path):
        """Worktree path resolving outside repo root fails."""
        cfg = SpecStorageConfig(worktree_path="../../escape")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.worktree_path" in errors[0]
        assert "outside repository root" in errors[0]

    def test_worktree_path_empty(self, repo_root: Path):
        """Empty worktree path fails."""
        cfg = SpecStorageConfig(worktree_path="")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) == 1
        assert "spec_storage.worktree_path" in errors[0]
        assert "empty" in errors[0]

    def test_worktree_path_valid_nested(self, repo_root: Path):
        """Valid nested path passes."""
        cfg = SpecStorageConfig(worktree_path="some/nested/path")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    def test_worktree_path_at_root(self, repo_root: Path):
        """Path at repo root passes (e.g. 'kitty-specs')."""
        cfg = SpecStorageConfig(worktree_path="kitty-specs")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    # --- auto_push validation ---

    def test_auto_push_true_valid(self, repo_root: Path):
        """auto_push=True passes."""
        cfg = SpecStorageConfig(auto_push=True)
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    def test_auto_push_false_valid(self, repo_root: Path):
        """auto_push=False passes."""
        cfg = SpecStorageConfig(auto_push=False)
        errors = validate_spec_storage_config(cfg, repo_root)
        assert errors == []

    # --- Multiple errors ---

    def test_multiple_errors_reported(self, repo_root: Path):
        """Multiple validation errors are all reported."""
        cfg = SpecStorageConfig(
            branch_name="",
            worktree_path="",
        )
        errors = validate_spec_storage_config(cfg, repo_root)
        assert len(errors) >= 2
        key_names = [e.split(":")[0] for e in errors]
        assert "spec_storage.branch_name" in key_names
        assert "spec_storage.worktree_path" in key_names

    # --- Error message quality ---

    def test_error_mentions_key_name(self, repo_root: Path):
        """Error messages include the exact config key."""
        cfg = SpecStorageConfig(branch_name="bad branch")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert any("spec_storage.branch_name" in e for e in errors)

    def test_error_mentions_value(self, repo_root: Path):
        """Error messages include the offending value."""
        cfg = SpecStorageConfig(branch_name="bad branch")
        errors = validate_spec_storage_config(cfg, repo_root)
        assert any("'bad branch'" in e for e in errors)


class TestValidateSpecStorageRaw:
    """Test validate_spec_storage_raw() for type-safety on raw YAML data."""

    def test_valid_raw_data(self, repo_root: Path):
        """Valid raw data passes validation."""
        raw = {
            "branch_name": "kitty-specs",
            "worktree_path": "kitty-specs",
            "auto_push": False,
        }
        errors = validate_spec_storage_raw(raw, repo_root)
        assert errors == []

    def test_auto_push_string_rejected(self, repo_root: Path):
        """String 'yes' for auto_push is rejected."""
        raw = {"auto_push": "yes"}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert len(errors) == 1
        assert "spec_storage.auto_push" in errors[0]
        assert "boolean" in errors[0]

    def test_auto_push_string_true_rejected(self, repo_root: Path):
        """String 'true' for auto_push is rejected."""
        raw = {"auto_push": "true"}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert len(errors) == 1
        assert "spec_storage.auto_push" in errors[0]

    def test_auto_push_int_rejected(self, repo_root: Path):
        """Integer 1 for auto_push is rejected."""
        raw = {"auto_push": 1}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert len(errors) == 1
        assert "spec_storage.auto_push" in errors[0]

    def test_non_dict_rejected(self, repo_root: Path):
        """Non-dict raw data is rejected."""
        errors = validate_spec_storage_raw("not-a-dict", repo_root)  # type: ignore[arg-type]
        assert len(errors) == 1
        assert "expected a mapping" in errors[0]

    def test_invalid_branch_in_raw(self, repo_root: Path):
        """Invalid branch name in raw data is caught."""
        raw = {"branch_name": "bad branch"}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert any("branch_name" in e for e in errors)

    def test_worktree_path_escape_in_raw(self, repo_root: Path):
        """Worktree path escaping root in raw data is caught."""
        raw = {"worktree_path": "../../outside"}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert any("worktree_path" in e for e in errors)

    def test_missing_keys_use_defaults(self, repo_root: Path):
        """Missing keys in raw data fall back to valid defaults."""
        raw: dict = {}
        errors = validate_spec_storage_raw(raw, repo_root)
        assert errors == []
