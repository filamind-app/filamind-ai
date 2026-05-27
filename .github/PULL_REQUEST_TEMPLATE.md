<!--
Before opening a PR, please check:

1. Is your change for `main` (UI, daemon, agents, providers, i18n) or for a `device/*` branch (INFO arch, build scripts, binaries)? If unsure, target `main`.

2. PRs from `device/*` → `main` should NOT exist by design. The branches are permanently parallel. Updates flow `main` → device/* via cherry-pick, never the other way.

3. Did you add a `CHANGELOG.md` entry under the next version (Added / Changed / Fixed / Security / …)?

4. Did you add **both** `en.json` AND `ar.json` keys for any new user-visible string? Arabic must be natural, not literal.

5. For security-sensitive changes (auth, file paths, network), please note the threat model briefly below.
-->

## Summary
<!-- 1–3 bullet points -->

## Why
<!-- The motivation. Skip if obvious from Summary. -->

## How to test
<!-- A checklist of what a reviewer (or future-you) should verify -->
- [ ]

## Risk / threat model
<!-- For auth, path, network, crypto changes only. Otherwise delete. -->

## i18n
<!-- For UI changes only. Otherwise delete. -->
- [ ] en.json updated
- [ ] ar.json updated (natural Arabic, not literal)
