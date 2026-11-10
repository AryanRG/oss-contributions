#!/usr/bin/env python3
"""Build a public list of merged external pull requests from GitHub."""

from __future__ import annotations

import json
import re
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


# Display grouping only. A repository missing from this map is still listed, under "Other".
AREAS: dict[str, tuple[str, ...]] = {
    "OCR, documents and NLP": (
        "tesseract-ocr/tesseract",
        "docling-project/docling",
        "RapidAI/RapidOCR",
        "mindee/doctr",
        "stanfordnlp/stanza",
        "chardet/chardet",
        "jawah/charset_normalizer",
        "rapidfuzz/RapidFuzz",
        "mammothb/symspellpy",
        "jaraco/inflect",
    ),
    "Markdown and parsing": (
        "executablebooks/markdown-it-py",
        "executablebooks/mdit-py-plugins",
        "executablebooks/MyST-Parser",
        "lepture/mistune",
    ),
    "Machine learning and statistics": (
        "statsmodels/statsmodels",
        "unit8co/darts",
        "tslearn-team/tslearn",
        "KevinMusgrave/pytorch-metric-learning",
        "TylerYep/torchinfo",
        "SimplexLab/TorchJD",
        "csinva/imodels",
        "MaxHalford/prince",
        "david-cortes/contextualbandits",
        "shankarpandala/lazypredict",
        "rodrigo-arenas/Sklearn-genetic-opt",
        "sknetwork-team/scikit-network",
        "skops-dev/skops",
        "skrub-data/skrub",
        "zillow/quantile-forest",
        "sbi-dev/sbi",
        "CyberAgentAILab/cmaes",
        "optuna/optunahub",
        "neuropsychology/NeuroKit",
        "Farama-Foundation/PettingZoo",
    ),
    "Arrays and scientific computing": (
        "pydata/xarray",
        "data-apis/array-api-compat",
        "dgasmith/opt_einsum",
        "patrick-kidger/lineax",
        "tensorly/tensorly",
    ),
    "LLM tooling, data and databases": (
        "feast-dev/feast",
        "datachain-ai/datachain",
        "langfuse/langfuse-python",
        "Mirascope/mirascope",
        "weaviate/weaviate-python-client",
        "dpkp/kafka-python",
        "psycopg/psycopg",
        "kayak/pypika",
        "fsspec/filesystem_spec",
    ),
    "Networking, async and protocols": (
        "agronholm/anyio",
        "agronholm/exceptiongroup",
        "websocket-client/websocket-client",
        "rthalley/dnspython",
        "graphql-python/graphql-core",
        "openlawlibrary/pygls",
    ),
    "Packaging and developer tools": (
        "pypa/pipx",
        "pypa/flit",
        "pypa/distlib",
        "pypa/pyproject-metadata",
        "pypa/packaging",
        "python-poetry/poetry-core",
        "tox-dev/filelock",
        "tox-dev/platformdirs",
        "tox-dev/pyproject-api",
        "python-cmd2/cmd2",
        "msgspec/msgspec",
        "nhairs/python-json-logger",
        "cdgriffith/Box",
    ),
    "Java": (
        "apache/commons-codec",
        "apache/commons-io",
        "apache/commons-lang",
        "apache/commons-numbers",
        "apache/poi",
        "Kong/unirest-java",
    ),
}
OTHER = "Other"
AREA_BY_REPO = {
    repo.casefold(): area for area, repos in AREAS.items() for repo in repos
}

# Hand-written summaries for titles that read poorly once their prefix is removed.
SUMMARY_OVERRIDES = {
    "docling-project/docling#4818": "Preserve table footnotes in JATS documents",
    "pypa/packaging#1454": "Fix inherited metadata class field validation and serialization",
}

# "[LANG-1838] ", "[Fix] ", "fix(jats): ", "BUG: ", "FIX " and leading emoji.
_TAG = re.compile(r"^\[[^\]]{1,24}\]\s*")
_PREFIX = re.compile(r"^(?:(?i:fix|bug|bugfix)(?:\([^)]{1,32}\))?!?:\s*|FIX\s+)")
_ESCAPE = re.compile(r"([\\`*\[\]<>|])")


def clean_title(title: str) -> str:
    """Turn a PR title into a short plain-text summary that is safe in Markdown."""
    text = " ".join(title.split())
    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"^[^\w\[(\"'`]+", "", text)
        text = _TAG.sub("", text)
        text = _PREFIX.sub("", text, count=1)
    if not text:
        text = " ".join(title.split())
    text = text[0].upper() + text[1:]
    return _ESCAPE.sub(r"\\\1", text.replace("&", "&amp;"))


def summary(pr: dict) -> str:
    key = f"{pr['repository']['nameWithOwner']}#{pr['number']}".casefold()
    for override_key, text in SUMMARY_OVERRIDES.items():
        if override_key.casefold() == key:
            return clean_title(text)
    return clean_title(pr.get("title") or "")


def markdown(prs: list[dict]) -> str:
    by_area: dict[str, list[dict]] = defaultdict(list)
    projects = set()
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        projects.add(repo.casefold())
        by_area[AREA_BY_REPO.get(repo.casefold(), OTHER)].append(pr)

    lines = [
        "# Open-source contributions",
        "",
        "Merged pull requests by [@AryanRG](https://github.com/AryanRG) "
        "in external public repositories, grouped by area. Each entry links "
        "to the upstream PR and its review history.",
        "",
        f"**Merged PRs: {len(prs)} · Projects: {len(projects)}**",
    ]
    for area in [*AREAS, OTHER]:
        entries = by_area.get(area)
        if not entries:
            continue
        lines.extend(["", f"## {area}", ""])
        for pr in entries:
            repo = pr["repository"]["nameWithOwner"]
            lines.append(
                f"- [{repo}](https://github.com/{repo}): "
                f"{summary(pr)} "
                f"([#{pr['number']}]({pr['url']}))"
            )
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
