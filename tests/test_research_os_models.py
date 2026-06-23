import unittest

from research_os.models import ResearchFact


class ResearchModelsTest(unittest.TestCase):
    def test_fact_snippet_is_shortened_for_notion_and_copyright_safety(self):
        fact = ResearchFact(
            table="category",
            fact="結婚相談所は入会から成婚退会まで複数ステップで進む",
            category="Step",
            source_url="https://example.com/article",
            source_title="Example",
            evidence_snippet="あ" * 500,
            confidence="High",
            research_run_id="run-1",
        )

        self.assertLessEqual(len(fact.safe_snippet()), 180)

    def test_fact_without_source_url_is_not_valid_for_notion_row(self):
        fact = ResearchFact(
            table="target",
            fact="ユーザーは料金に不安を持つ",
            category="Concern",
            source_url="",
            source_title="",
            evidence_snippet="料金が高そう",
            confidence="Low",
            research_run_id="run-1",
        )

        self.assertFalse(fact.is_usable())


if __name__ == "__main__":
    unittest.main()
