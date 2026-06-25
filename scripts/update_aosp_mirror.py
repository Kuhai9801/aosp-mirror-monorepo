#!/usr/bin/env python3
"""Refresh a superproject that tracks every public repo in github.com/aosp-mirror."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_ROOT = "https://api.github.com"
DEFAULT_OWNER = "aosp-mirror"
DEFAULT_REPO_DIR = "repos"
INFRA_REPOS = {".allstar", ".github"}


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def github_request(path: str, token: str | None) -> tuple[object, dict[str, str]]:
    request = urllib.request.Request(f"{API_ROOT}{path}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "aosp-mirror-monorepo-sync")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.headers.items()}
    return json.loads(body), headers


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        url_part, _, rel_part = part.partition(";")
        if 'rel="next"' not in rel_part:
            continue
        url = url_part.strip()[1:-1]
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.path}?{parsed.query}"
    return None


def fetch_repos(owner: str, token: str | None) -> list[dict[str, object]]:
    repos: list[dict[str, object]] = []
    path: str | None = f"/orgs/{owner}/repos?per_page=100&type=public&sort=full_name"

    while path:
        payload, headers = github_request(path, token)
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected GitHub API response for {path}: {payload!r}")
        repos.extend(payload)
        path = parse_next_link(headers.get("link"))

    repos.sort(key=lambda repo: str(repo["name"]))
    return repos


def repo_record(repo: dict[str, object]) -> dict[str, object]:
    return {
        "name": repo["name"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "clone_url": repo["clone_url"],
        "ssh_url": repo["ssh_url"],
        "mirror_url": repo.get("mirror_url"),
        "default_branch": repo.get("default_branch") or "main",
        "archived": repo.get("archived", False),
        "fork": repo.get("fork", False),
        "language": repo.get("language"),
        "size": repo.get("size"),
        "pushed_at": repo.get("pushed_at"),
        "updated_at": repo.get("updated_at"),
    }


def write_manifest(root: Path, records: list[dict[str, object]]) -> None:
    manifest_dir = root / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "source": "https://github.com/aosp-mirror",
        "canonical_aosp_source": "https://android.googlesource.com/",
        "generated_at_unix": int(time.time()),
        "repo_count": len(records),
        "repos": records,
    }
    (manifest_dir / "aosp-mirror-repos.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (manifest_dir / "aosp-mirror-repos.txt").write_text(
        "".join(f"{record['name']}\n" for record in records),
        encoding="utf-8",
    )


def git_root(start: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False)
    if proc.returncode == 0:
        return Path(proc.stdout.strip()).resolve()
    run(["git", "init"], cwd=start)
    return start.resolve()


def ensure_submodule(root: Path, record: dict[str, object], repo_dir: str, protocol: str) -> Path:
    name = str(record["name"])
    branch = str(record["default_branch"])
    url_key = "ssh_url" if protocol == "ssh" else "clone_url"
    url = str(record[url_key])
    path = root / repo_dir / name

    if path.exists():
        run(["git", "-C", str(path), "remote", "set-url", "origin", url])
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "git",
            "submodule",
            "add",
            "--force",
            "--depth",
            "1",
            "--branch",
            branch,
            "--name",
            name,
            url,
            str(path.relative_to(root)),
        ],
        cwd=root,
    )
    return path


def fetch_branch(path: Path, branch: str, deepen: int | None = None) -> None:
    cmd = [
        "git",
        "-C",
        str(path),
        "fetch",
        "--prune",
        "--no-tags",
        "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
    ]
    if deepen is None:
        cmd.insert(4, "--depth=50")
    else:
        cmd.insert(4, f"--deepen={deepen}")
    run(cmd)


def rev_parse(path: Path, rev: str) -> str | None:
    proc = run(["git", "-C", str(path), "rev-parse", "--verify", rev], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def is_ancestor(path: Path, current: str, target: str) -> bool:
    proc = run(["git", "-C", str(path), "merge-base", "--is-ancestor", current, target], check=False)
    return proc.returncode == 0


def update_submodule(root: Path, record: dict[str, object], repo_dir: str, protocol: str) -> dict[str, object]:
    name = str(record["name"])
    branch = str(record["default_branch"])
    path = ensure_submodule(root, record, repo_dir, protocol)

    fetch_branch(path, branch)
    target = rev_parse(path, f"refs/remotes/origin/{branch}")
    if target is None:
        return {"name": name, "branch": branch, "status": "missing-branch"}

    current = rev_parse(path, "HEAD")
    if current and current != target and not is_ancestor(path, current, target):
        fetch_branch(path, branch, deepen=1000)
        if not is_ancestor(path, current, target):
            return {
                "name": name,
                "branch": branch,
                "status": "non-fast-forward",
                "current": current,
                "target": target,
            }

    run(["git", "-C", str(path), "checkout", "--detach", target])
    run(["git", "add", str(path.relative_to(root))], cwd=root)
    return {
        "name": name,
        "branch": branch,
        "status": "updated" if current != target else "unchanged",
        "current": current,
        "target": target,
    }


def write_lock(root: Path, updates: list[dict[str, object]]) -> None:
    lock_path = root / "manifest" / "aosp-mirror-lock.tsv"
    lines = ["repo\tbranch\tstatus\tcurrent\ttarget\n"]
    for update in sorted(updates, key=lambda item: str(item["name"])):
        current = update.get("current") or "-"
        target = update.get("target") or "-"
        lines.append(
            "{name}\t{branch}\t{status}\t{current}\t{target}\n".format(
                name=update.get("name", ""),
                branch=update.get("branch", ""),
                status=update.get("status", ""),
                current=current,
                target=target,
            )
        )
    lock_path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo-dir", default=DEFAULT_REPO_DIR)
    parser.add_argument("--protocol", choices=("https", "ssh"), default="https")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--exclude-infra", action="store_true", help="skip .github and .allstar")
    parser.add_argument("--limit", type=int, default=0, help="limit repos for smoke testing")
    args = parser.parse_args()

    start = Path.cwd()
    root = git_root(start)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    records = [repo_record(repo) for repo in fetch_repos(args.owner, token)]
    if args.exclude_infra:
        records = [record for record in records if record["name"] not in INFRA_REPOS]
    if args.limit:
        records = records[: args.limit]

    write_manifest(root, records)
    updates: list[dict[str, object]] = []
    if not args.metadata_only:
        for record in records:
            print(f"::group::sync {record['name']}")
            try:
                updates.append(update_submodule(root, record, args.repo_dir, args.protocol))
            finally:
                print("::endgroup::")
        write_lock(root, updates)
    else:
        write_lock(root, [{"name": record["name"], "branch": record["default_branch"], "status": "metadata-only"} for record in records])

    run(["git", "add", "manifest", ".gitmodules"], cwd=root, check=False)
    print(f"tracked {len(records)} repositories from github.com/{args.owner}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
