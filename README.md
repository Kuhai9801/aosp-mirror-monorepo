# AOSP Mirror Monorepo

This repository is a control-plane monorepo for the public repositories in
`github.com/aosp-mirror`, with selected security-review source trees vendored
directly for default-branch scanners.

Important source notes:

- `github.com/aosp-mirror` is a GitHub mirror organization, and GitHub currently
  marks it archived.
- The canonical Android source is hosted by Google at
  `https://android.googlesource.com/`.
- Security bugs that affect Android or Pixel components should follow Google's
  Android and Google Devices Security Reward Program rules.

## Layout

- `manifest/aosp-mirror-repos.json` records the public repositories discovered
  from the GitHub organization.
- `manifest/aosp-mirror-repos.txt` is a compact name list.
- `manifest/aosp-mirror-lock.tsv` records the last sync status and target SHA.
- `repos/<name>` stores submodule gitlinks for most mirror repositories.
- `repos/platform_frameworks_base` and `repos/platform_system_core` are vendored
  scan source trees so default-branch-only scanners can inspect those components
  without initializing submodules. `platform_frameworks_base` is a curated
  security slice, not the full upstream tree.
- `scripts/update_aosp_mirror.py` refreshes metadata and fast-forwards submodule
  pointers.

## Local Sync

Refresh metadata only:

```sh
python3 scripts/update_aosp_mirror.py --metadata-only
```

Materialize and fast-forward all tracked mirror repositories:

```sh
python3 scripts/update_aosp_mirror.py
```

Fast-forward gitlink pointers without cloning repository contents:

```sh
python3 scripts/update_aosp_mirror.py --gitlinks-only
```

## CI

`.github/workflows/fast-forward.yml` runs on `*/5 * * * *` and by manual
dispatch. The job refreshes the mirror metadata, fast-forwards submodule
pointers for non-vendored repositories, refreshes vendored scan source trees,
commits changes, and pushes back to this repository.

GitHub scheduled workflows are best-effort; the cron asks for every 5 minutes,
but GitHub can delay or skip runs during load or after repository inactivity.

## Scope For Bug Bounty Work

Use this as a local research mirror. Before reporting anything, confirm the
issue against canonical AOSP source, current release branches, and the active
Google program rules. Do not assume a stale GitHub mirror commit is in reward
scope without checking the program language.

## Vendored Scan Sources

The default branch vendors these components for Codex Security scans:

- `platform_frameworks_base`: `repos/platform_frameworks_base` at upstream
  `main` commit `1cdfff555f4a21f71ccc978290e2e212e2f8b168`, limited to:
  - `core/java/android/app/AppOpsManager.java`
  - `core/java/android/app/admin`
  - `core/java/android/content/pm`
  - `core/java/android/permission`
  - `core/java/android/security`
  - `packages/SettingsProvider`
  - `services/core/java/com/android/server/accounts`
  - `services/core/java/com/android/server/appop`
  - `services/core/java/com/android/server/biometrics`
  - `services/core/java/com/android/server/locksettings`
  - `services/core/java/com/android/server/permission`
  - `services/core/java/com/android/server/pm`
  - `services/core/java/com/android/server/policy`
  - `services/core/java/com/android/server/role`
  - `services/core/java/com/android/server/security`
  - `services/core/java/com/android/server/uri`
- `platform_system_core`: full `repos/platform_system_core` at upstream `main`
  commit `a3b721a32242006b59cb12bd62c9133632af3a2d`
