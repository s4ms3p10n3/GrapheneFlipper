#!/usr/bin/env python3
"""Publish a stable GitHub release after the Drone plugin uploads its assets."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"


def request(method: str, url: str, token: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "GrapheneFlipper-Drone-CI",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("DRONE_REPO", "").strip()
    tag = os.environ.get("DRONE_TAG", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is empty; configure Drone secret github_apikey"
        )
    if repo.count("/") != 1 or not tag:
        raise RuntimeError("DRONE_REPO or DRONE_TAG is missing")

    owner, name = repo.split("/", 1)
    repo_api = (
        f"{API_ROOT}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}"
    )
    encoded_tag = urllib.parse.quote(tag, safe="")
    release = request("GET", f"{repo_api}/releases/tags/{encoded_tag}", token)

    assets = request(
        "GET", f"{repo_api}/releases/{release['id']}/assets?per_page=100", token
    )
    if not assets:
        raise RuntimeError(
            f"Release {tag} has no uploaded assets; refusing to publish it"
        )

    if release.get("draft") is False:
        if release.get("prerelease") is False:
            print(
                f"Stable release {tag} is already published: {release.get('html_url', '')}"
            )
            return 0
        raise RuntimeError(
            f"Release {tag} is already published as a prerelease; refusing to change it"
        )

    published = request(
        "PATCH",
        f"{repo_api}/releases/{release['id']}",
        token,
        {"draft": False, "prerelease": False, "make_latest": "true"},
    )
    print(
        f"Published stable release: {published.get('html_url', f'https://github.com/{repo}/releases/tag/{tag}')}"
    )
    print(f"Published {len(assets)} release assets")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
