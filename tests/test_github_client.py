import unittest
from app.core.github_client import parse_github_url
from app.core.prioritizer import score_filepath


class TestGitHubClient(unittest.TestCase):
    def test_parse_github_url(self):
        owner, repo = parse_github_url("https://github.com/facebook/react")
        self.assertEqual(owner, "facebook")
        self.assertEqual(repo, "react")

        owner, repo = parse_github_url("https://github.com/facebook/react.git")
        self.assertEqual(owner, "facebook")
        self.assertEqual(repo, "react")

    def test_score_filepath(self):
        self.assertEqual(score_filepath("README.md"), 0)
        self.assertEqual(score_filepath("package.json"), 0)
        self.assertEqual(score_filepath("src/components/Button.tsx"), 1)
        self.assertEqual(score_filepath("src/main.ts"), 1)
        self.assertEqual(score_filepath("tsconfig.json"), 3)


if __name__ == "__main__":
    unittest.main()
