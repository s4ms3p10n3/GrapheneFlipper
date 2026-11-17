#!/usr/bin/env python3
"""Publish this Drone dev build as a GitHub prerelease (stdlib only)."""

from __future__ import annotations

import glob
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API returned HTTP {status}: {message}")
        self.status = status


def api_request(
    method: str, url: str, token: str, payload=None, content_type="application/json"
):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "GrapheneFlipper-Drone-CI",
    }
    if data is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubAPIError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc


def get_release_for_tag(repo_api: str, tag: str, token: str):
    url = f"{repo_api}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    try:
        return api_request("GET", url, token)
    except GitHubAPIError as exc:
        if exc.status == 404:
            return None
        raise


def list_release_assets(repo_api: str, release_id: int, token: str):
    assets = []
    page = 1
    while True:
        url = f"{repo_api}/releases/{release_id}/assets?per_page=100&page={page}"
        batch = api_request("GET", url, token)
        assets.extend(batch)
        if len(batch) < 100:
            return assets
        page += 1


def upload_asset(upload_url: str, file_path: Path, token: str):
    # GitHub returns a URL template ending in {?name,label}.
    base_url = upload_url.split("{", 1)[0]
    query = urllib.parse.urlencode({"name": file_path.name})
    url = f"{base_url}?{query}"
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    data = file_path.read_bytes()
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "User-Agent": "GrapheneFlipper-Drone-CI",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Uploaded {file_path} ({len(data)} bytes)")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubAPIError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not upload {file_path.name}: {exc.reason}") from exc


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is empty; configure Drone secret github_apikey"
        )

    repo = os.environ.get("DRONE_REPO", "").strip()
    if not repo:
        owner = os.environ.get("DRONE_REPO_OWNER", "").strip()
        name = os.environ.get("DRONE_REPO_NAME", "").strip()
        repo = f"{owner}/{name}" if owner and name else ""
    if repo.count("/") != 1:
        raise RuntimeError(
            "Could not determine repository from DRONE_REPO or DRONE_REPO_OWNER/DRONE_REPO_NAME"
        )

    build_number = os.environ.get("DRONE_BUILD_NUMBER", "").strip()
    commit = os.environ.get("DRONE_COMMIT_SHA", "").strip()
    branch = os.environ.get("DRONE_BRANCH", "dev").strip() or "dev"
    build_link = os.environ.get("DRONE_BUILD_LINK", "").strip()
    if not build_number or not build_number.isdigit():
        raise RuntimeError(f"Invalid or missing DRONE_BUILD_NUMBER: {build_number!r}")
    if not commit:
        raise RuntimeError("DRONE_COMMIT_SHA is empty")

    owner, name = repo.split("/", 1)
    repo_api = (
        f"{API_ROOT}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}"
    )
    tag = f"dev-{build_number}"
    title = f"GrapheneFlipper development build #{build_number}"

    patterns = (
        "dev/*.tgz",
        "dev/*.zip",
        "artifacts-clean/*.tgz",
        "artifacts-clean/*.zip",
        "artifacts-extra-apps/*.tgz",
        "artifacts-extra-apps/*.zip",
    )
    file_names = sorted(
        {p for pattern in patterns for p in glob.glob(pattern) if Path(p).is_file()}
    )
    if not file_names:
        raise RuntimeError(
            "No firmware release assets found in dev/, artifacts-clean/, or artifacts-extra-apps/"
        )
    files = [Path(p) for p in file_names]

    body_lines = [
        f"Automated GrapheneFlipper development prerelease #{build_number}.",
        "",
        f"Branch: `{branch}`",
        f"Commit: `{commit}`",
        "",
        "This is an automatically generated development build. It may contain unfinished changes and is not a stable release.",
    ]
    if build_link:
        body_lines.extend(["", f"Drone build: {build_link}"])
    body = "\n".join(body_lines)

    release = get_release_for_tag(repo_api, tag, token)
    if release is None:
        print(f"Creating GitHub prerelease {tag} for {repo} at {commit}")
        release = api_request(
            "POST",
            f"{repo_api}/releases",
            token,
            {
                "tag_name": tag,
                "target_commitish": commit,
                "name": title,
                "body": body,
                "draft": False,
                "prerelease": True,
                "make_latest": "false",
            },
        )
    else:
        print(f"Updating existing GitHub prerelease {tag}")
        release = api_request(
            "PATCH",
            f"{repo_api}/releases/{release['id']}",
            token,
            {
                "name": title,
                "body": body,
                "draft": False,
                "prerelease": True,
            },
        )

    release_id = release["id"]
    upload_url = release["upload_url"]
    wanted_names = {p.name for p in files}
    for asset in list_release_assets(repo_api, release_id, token):
        if asset.get("name") in wanted_names:
            print(f"Removing previous asset {asset['name']} before replacement")
            api_request("DELETE", f"{repo_api}/releases/assets/{asset['id']}", token)

    for file_path in files:
        upload_asset(upload_url, file_path, token)

    html_url = release.get("html_url", f"https://github.com/{repo}/releases/tag/{tag}")
    print(f"Published prerelease: {html_url}")
    print(f"Uploaded {len(files)} firmware assets")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
