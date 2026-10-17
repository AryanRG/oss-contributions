#!/usr/bin/env python3
"""Build a public list of merged external pull requests from GitHub."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path


ACCOUNT = "AryanRG"
EXCLUDED_OWNERS = {"aryanrg", "sapper-software"}
QUERY = """
query($cursor: String) {
  search(query: "is:pr author:AryanRG is:merged -user:Sapper-Software -user:AryanRG",
         type: ISSUE, first: 100, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        mergedAt
        author { login }
        repository {
          nameWithOwner
          isPrivate
          owner { login }
        }
      }
    }
  }
}
"""


def fetch_merged() -> list[dict]:
    """Fetch every search page and fail closed on incomplete API results."""
    cursor = None
    results: list[dict] = []
    while True:
        command = ["gh", "api", "graphql", "-f", f"query={QUERY}"]
        if cursor is not None:
            command.extend(["-f", f"cursor={cursor}"])
        response = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(response.stdout)
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        search = payload["data"]["search"]
        if search["issueCount"] > 1000:
            raise RuntimeError("GitHub search's 1,000-result cap would truncate the list")
        results.extend(search["nodes"])
        if not search["pageInfo"]["hasNextPage"]:
            break
        next_cursor = search["pageInfo"]["endCursor"]
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("GitHub returned an invalid pagination cursor")
        cursor = next_cursor
    return results


def verified_external_prs(nodes: list[dict]) -> list[dict]:
    """Keep only merged, public, externally owned PRs by this account."""
    unique: dict[str, dict] = {}
    for pr in nodes:
        if not pr:
            continue
        repo = pr.get("repository") or {}
        author = pr.get("author") or {}
        owner = repo.get("owner") or {}
        if (
            not pr.get("mergedAt")
            or author.get("login", "").casefold() != ACCOUNT.casefold()
            or repo.get("isPrivate") is not False
            or owner.get("login", "").casefold() in EXCLUDED_OWNERS
            or not repo.get("nameWithOwner")
            or not pr.get("url")
        ):
            continue
        unique[pr["url"]] = pr
    return sorted(unique.values(), key=lambda pr: (pr["repository"]["nameWithOwner"].casefold(), pr["number"]))


def markdown(prs: list[dict]) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for pr in prs:
        grouped[pr["repository"]["nameWithOwner"]].append(pr)

    lines = [
        "# Open-source contributions",
        "",
        "Merged pull requests by [@AryanRG](https://github.com/AryanRG) "
        "in external public repositories. Each link leads to the upstream PR "
        "and its review history.",
        "",
        f"**Merged PRs: {len(prs)} · Projects: {len(grouped)}**",
        "",
        "| Project | Merged pull requests |",
        "| --- | --- |",
    ]
    for repo in sorted(grouped, key=str.casefold):
        links = " · ".join(
            f"[#{pr['number']}]({pr['url']})" for pr in grouped[repo]
        )
        lines.append(f"| [{repo}](https://github.com/{repo}) | {links} |")
    lines.extend(
        [
            "",
            "This page is generated from GitHub's merged-PR records. Open, draft, "
            "and closed-unmerged PRs are not counted.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parent
    prs = verified_external_prs(fetch_merged())
    if not prs:
        raise RuntimeError("No verified external merges found; refusing to replace README")
    (root / "README.md").write_text(markdown(prs), encoding="utf-8")
    print(f"Wrote {len(prs)} verified merges across {len({pr['repository']['nameWithOwner'] for pr in prs})} projects")


if __name__ == "__main__":
    main()
