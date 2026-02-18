---
description: Merge a feature's landing branch into the upstream branch (e.g., main) for local integration
scripts:
  sh: "spec-kitty agent feature integrate"
  ps: "spec-kitty agent"
---
**Path reference rule:** When you mention directories or files, provide either the absolute path or a path relative to the project root (for example, `kitty-specs/<feature>/tasks/`). Never refer to a folder by name alone.

*Path: [templates/commands/integrate.md](templates/commands/integrate.md)*


# Integrate Landing Branch

This command merges a feature's **landing branch** into the **upstream branch** (e.g., `main`) for local integration.

## Workflow Context

The landing branch workflow has two steps:

1. **`spec-kitty merge`** - Merges WP branches into the feature's landing branch
2. **`spec-kitty integrate`** - Merges the landing branch into upstream (this command)

The landing branch is **NEVER deleted** by either command. It remains available for:
- Upstream PR submission
- Future changes and amendments
- Rebasing onto updated upstream

## Prerequisites

Before running this command:

1. All WP branches should be merged into the landing branch (`spec-kitty merge`)
2. Working directory must be clean (no uncommitted changes)
3. The landing branch must exist

## Usage

### Basic integration
```bash
spec-kitty integrate
```

### With options
```bash
# Squash all landing branch commits into one
spec-kitty integrate --strategy squash

# Push upstream branch after integrating
spec-kitty integrate --push

# Integrate a specific feature
spec-kitty integrate --feature 010-my-feature

# Preview without executing
spec-kitty integrate --dry-run
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--feature` | Feature slug (auto-detected from branch) | auto |
| `--strategy` | Integration strategy: `merge` or `squash` | `merge` |
| `--push` | Push upstream branch to origin | no push |
| `--dry-run` | Show what would be done without executing | off |

## What This Command Does

1. **Detects** the feature slug from current branch or `--feature` flag
2. **Resolves** the landing branch (from meta.json `target_branch`) and upstream branch (from meta.json `upstream_branch`)
3. **Switches** to the upstream branch (e.g., `main`)
4. **Updates** the upstream branch (`git pull --ff-only`)
5. **Merges** the landing branch using your chosen strategy
6. **Optionally pushes** to origin
7. **Preserves** the landing branch (never deleted)

## Important Notes

- The landing branch is never deleted by this command
- The upstream branch is determined from `meta.json` (field `upstream_branch`, defaults to `main`)
- For upstream PRs, push the landing branch directly instead of integrating first
