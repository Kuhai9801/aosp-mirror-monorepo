# AOSP Mirror Monorepo

This repository is a control-plane monorepo for the public repositories in
`github.com/aosp-mirror`.

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
- `repos/<name>` is where each mirror repository is checked out as a submodule.
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

## CI

`.github/workflows/fast-forward.yml` runs on `*/5 * * * *` and by manual
dispatch. The job refreshes the mirror metadata, fast-forwards each submodule to
its GitHub default branch when possible, commits changed pointers, and pushes
back to this repository.

GitHub scheduled workflows are best-effort; the cron asks for every 5 minutes,
but GitHub can delay or skip runs during load or after repository inactivity.

## Scope For Bug Bounty Work

Use this as a local research mirror. Before reporting anything, confirm the
issue against canonical AOSP source, current release branches, and the active
Google program rules. Do not assume a stale GitHub mirror commit is in reward
scope without checking the program language.
