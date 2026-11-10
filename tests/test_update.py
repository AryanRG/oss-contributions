import unittest

from update import AREAS, OTHER, clean_title, markdown, verified_external_prs


def pr(
    repo="tox-dev/filelock",
    owner="tox-dev",
    private=False,
    merged=True,
    number=855,
    title="A verified fix",
):
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/{repo}/pull/{number}",
        "mergedAt": "2026-10-17T12:56:02Z" if merged else None,
        "author": {"login": "AryanRG"},
        "repository": {
            "nameWithOwner": repo,
            "isPrivate": private,
            "owner": {"login": owner},
        },
    }


class ContributionsTests(unittest.TestCase):
    def test_only_external_public_merges(self):
        own = pr(repo="AryanRG/demo", owner="AryanRG")
        company = pr(repo="Sapper-Software/demo", owner="Sapper-Software")
        other_author = pr()
        other_author["author"] = {"login": "someone-else"}
        result = verified_external_prs(
            [pr(), pr(), pr(private=True), pr(merged=False), own, company, other_author]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["repository"]["nameWithOwner"], "tox-dev/filelock")

    def test_readme_links_to_upstream_pr_with_summary(self):
        output = markdown([pr()])
        self.assertIn("**Merged PRs: 1 · Projects: 1**", output)
        self.assertIn("## Packaging and developer tools", output)
        self.assertIn(
            "- [tox-dev/filelock](https://github.com/tox-dev/filelock): A verified fix "
            "([#855](https://github.com/tox-dev/filelock/pull/855))",
            output,
        )

    def test_areas_keep_fixed_order_and_unknown_projects_go_last(self):
        output = markdown(
            [
                pr(repo="new-org/new-project", owner="new-org", number=1),
                pr(repo="apache/poi", owner="apache", number=2),
                pr(repo="tesseract-ocr/tesseract", owner="tesseract-ocr", number=3),
                pr(repo="tesseract-ocr/tesseract", owner="tesseract-ocr", number=4),
            ]
        )
        headings = [line for line in output.splitlines() if line.startswith("## ")]
        self.assertEqual(
            headings, ["## OCR, documents and NLP", "## Java", f"## {OTHER}"]
        )
        self.assertIn("**Merged PRs: 4 · Projects: 3**", output)
        self.assertLess(output.index("pull/3)"), output.index("pull/4)"))

    def test_area_lookup_ignores_case(self):
        output = markdown([pr(repo="Apache/POI", owner="Apache")])
        self.assertIn("## Java", output)
        self.assertNotIn(f"## {OTHER}", output)

    def test_each_project_has_one_area(self):
        repos = [repo.casefold() for repos in AREAS.values() for repo in repos]
        self.assertEqual(len(repos), len(set(repos)))
        self.assertNotIn(OTHER, AREAS)

    def test_clean_title_strips_tags_and_prefixes(self):
        cases = {
            "[LANG-1838] Fix resource paths for unnamed packages": "Fix resource paths for unnamed packages",
            "fix(jats): preserve table footnotes": "Preserve table footnotes",
            "fix: align read_values rows": "Align read_values rows",
            "🐛 FIX: Avoid gfm_autolink hangs in link labels": "Avoid gfm_autolink hangs in link labels",
            "[MRG] Exclude self from radius queries": "Exclude self from radius queries",
            "[fix] Handle zero-width horizontal crops": "Handle zero-width horizontal crops",
            "BUG: Preserve Series prediction index": "Preserve Series prediction index",
            "FIX support relative output paths": "Support relative output paths",
            "Fix UTF-32 BOM detection": "Fix UTF-32 BOM detection",
            "Fixture cleanup: keep order": "Fixture cleanup: keep order",
            "  Copy   the initial mean ": "Copy the initial mean",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(clean_title(title), expected)

    def test_clean_title_escapes_markdown(self):
        self.assertEqual(
            clean_title("Handle `a|b` in [x](y) <b> & *c*"),
            r"Handle \`a\|b\` in \[x\](y) \<b\> &amp; \*c\*",
        )

    def test_summary_override_replaces_title(self):
        output = markdown(
            [
                pr(
                    repo="pypa/packaging",
                    owner="pypa",
                    number=1454,
                    title="fix: inherited metadata class field validation",
                )
            ]
        )
        self.assertIn(
            ": Fix inherited metadata class field validation and serialization ([#1454]",
            output,
        )

    def test_clean_title_never_returns_empty(self):
        self.assertEqual(clean_title("fix:"), "Fix:")
        self.assertEqual(clean_title("[Fix]"), "\\[Fix\\]")


if __name__ == "__main__":
    unittest.main()
