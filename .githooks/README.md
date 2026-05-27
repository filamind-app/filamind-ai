# Git hooks for Filamind AI

This directory holds shared git hooks that everyone working on the repo should run.

## One-time install (per clone)

After cloning, tell your local git to look here for hooks:

```bash
git config core.hooksPath .githooks
```

(Or set it globally on this machine: `git config --global core.hooksPath ~/.githooks` and symlink — but per-repo is simpler.)

## What each hook does

### `pre-push`
Blocks two dangerous operations on **protected branches** (`main`, `device/*`):
- **Force-pushes** (non-fast-forward updates). Stops accidental history rewrites that would scrub other contributors' commits.
- **Branch deletions**. Stops accidentally deleting `main` or a device branch from the remote.

**Bypass for legitimate emergencies** (e.g., scrubbing a leaked secret from history):

```bash
FORCE_PUSH_ALLOW=1 git push --force origin main
```

The bypass is intentional — security incidents sometimes require a one-time history rewrite.

### Why this matters

GitHub-side branch protection ("Branch protection rules" / "Rulesets") requires GitHub Pro for *private* repos. This local hook gives us the same defense from this machine for free. Anyone with push access from another machine still needs to install the hook themselves — that's what `core.hooksPath = .githooks` enforces once they run the install line above.
