import unittest

from update import markdown, verified_external_prs


def pr(repo="tox-dev/filelock", owner="tox-dev", private=False, merged=True):
    return {
        "number": 855,
        "title": "A verified fix",
        "url": "https://github.com/tox-dev/filelock/pull/855",
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

    def test_readme_links_to_upstream_pr(self):
        output = markdown([pr()])
        self.assertIn("**Merged PRs: 1 · Projects: 1**", output)
        self.assertIn("https://github.com/tox-dev/filelock/pull/855", output)
        self.assertNotIn("A verified fix", output)


if __name__ == "__main__":
    unittest.main()
