#!/usr/bin/env python3
"""Publish a Drone development build as a GitHub prerelease.

The release is created as a draft, assets are uploaded while it is mutable,
and only then is it published. This is required for repositories with
GitHub immutable releases enabled.
"""

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
        self.detail = message


def api_request(method: str, url: str, token: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "GrapheneFlipper-Drone-CI",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
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
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Uploaded {file_path.name} ({len(data)} bytes)", flush=True)
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubAPIError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not upload {file_path.name}: {exc.reason}") from exc


def expected_asset_sizes(files: list[Path]) -> dict[str, int]:
    result: dict[str, int] = {}
    for path in files:
        if path.name in result:
            raise RuntimeError(f"Duplicate release asset filename: {path.name}")
        result[path.name] = path.stat().st_size
    return result


def release_has_expected_assets(assets: list[dict], expected: dict[str, int]) -> bool:
    actual = {asset.get("name"): asset.get("size") for asset in assets}
    return actual == expected


def create_draft_release(
    repo_api: str, tag: str, commit: str, title: str, body: str, token: str
):
    return api_request(
        "POST",
        f"{repo_api}/releases",
        token,
        {
            "tag_name": tag,
            "target_commitish": commit,
            "name": title,
            "body": body,
            "draft": True,
            "prerelease": False,
            "make_latest": "true",
        },
    )


def choose_release(
    repo_api: str,
    base_tag: str,
    commit: str,
    title: str,
    body: str,
    expected: dict[str, int],
    token: str,
):
    """Resume a draft, reuse a complete published release, or choose a new tag.

    A published release is never modified. If a previous attempt published an
    incomplete immutable release, a revision suffix is used for the next try.
    """
    for revision in range(1, 101):
        tag = base_tag if revision == 1 else f"{base_tag}-r{revision}"
        release = get_release_for_tag(repo_api, tag, token)

        if release is None:
            print(f"Creating draft prerelease {tag}", flush=True)
            try:
                release = create_draft_release(
                    repo_api, tag, commit, title, body, token
                )
                return tag, release, False
            except GitHubAPIError as exc:
                # A tag left behind by a deleted immutable release may not be reusable.
                detail = exc.detail.lower()
                if exc.status == 422 and (
                    "already_exists" in detail or "already exists" in detail
                ):
                    print(
                        f"Tag {tag} is already reserved; trying another revision",
                        flush=True,
                    )
                    continue
                raise

        if release.get("draft") is True:
            print(f"Resuming existing draft prerelease {tag}", flush=True)
            release = api_request(
                "PATCH",
                f"{repo_api}/releases/{release['id']}",
                token,
                {"name": title, "body": body, "draft": True, "prerelease": False},
            )
            return tag, release, False

        assets = list_release_assets(repo_api, release["id"], token)
        if release_has_expected_assets(assets, expected):
            print(
                f"Prerelease {tag} is already published with the expected assets; nothing to do",
                flush=True,
            )
            return tag, release, True

        print(
            f"Published release {tag} is immutable or otherwise already published and its assets do not match; "
            "leaving it untouched and trying a new tag",
            flush=True,
        )

    raise RuntimeError(
        f"Could not find an available development prerelease tag based on {base_tag}"
    )


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
    if len(commit) < 8:
        raise RuntimeError("DRONE_COMMIT_SHA must contain at least 8 characters")

    owner, name = repo.split("/", 1)
    repo_api = (
        f"{API_ROOT}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}"
    )
    # Include the commit in the tag so a retried build cannot collide with an
    # older build that happened to use the same Drone build number.
    base_tag = f"dev-{build_number}-{commit[:8]}"
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
    expected = expected_asset_sizes(files)

    body_lines = [
        f"Automated GrapheneFlipper development Release #{build_number}.",
        "",
        f"Branch: `{branch}`",
        f"Commit: `{commit}`",
        "",
        "This is an automatically generated development build. It may contain unfinished changes and IS a stable release.",
    ]
    body = "\n".join(body_lines)

    tag, release, already_published = choose_release(
        repo_api, base_tag, commit, title, body, expected, token
    )
    if already_published:
        print(
            release.get("html_url", f"https://github.com/{repo}/releases/tag/{tag}"),
            flush=True,
        )
        return 0

    release_id = release["id"]
    upload_url = release["upload_url"]

    # Draft releases remain mutable. Clear any partial/stale assets from a
    # previous failed attempt, then upload the exact asset set for this build.
    for asset in list_release_assets(repo_api, release_id, token):
        print(f"Removing draft asset {asset.get('name')}", flush=True)
        api_request("DELETE", f"{repo_api}/releases/assets/{asset['id']}", token)

    for file_path in files:
        upload_asset(upload_url, file_path, token)

    uploaded_assets = list_release_assets(repo_api, release_id, token)
    if not release_has_expected_assets(uploaded_assets, expected):
        raise RuntimeError(
            "Uploaded asset list does not match the build outputs; keeping the release as a draft"
        )

    print(f"Publishing prerelease {tag}", flush=True)
    published = api_request(
        "PATCH",
        f"{repo_api}/releases/{release_id}",
        token,
        {"draft": False, "prerelease": False, "make_latest": "true"},
    )

    html_url = published.get(
        "html_url", f"https://github.com/{repo}/releases/tag/{tag}"
    )
    print(f"Published prerelease: {html_url}", flush=True)
    print(f"Uploaded and verified {len(files)} firmware assets", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
