import unittest

from research_os.models import CompetitorSiteRecord, ResearchFact
from research_os.notion_payloads import competitor_page_properties, fact_page_properties


class ResearchNotionPayloadTest(unittest.TestCase):
    def test_fact_page_properties_use_fact_as_title_and_source_url(self):
        fact = ResearchFact(
            table="category",
            fact="入会前に無料相談がある",
            category="Step",
            source_url="https://example.com",
            source_title="Example",
            evidence_snippet="無料相談",
            confidence="Medium",
            research_run_id="run-1",
        )

        props = fact_page_properties(fact)

        self.assertEqual(props["Fact"]["title"][0]["text"]["content"], "入会前に無料相談がある")
        self.assertEqual(props["Source URL"]["url"], "https://example.com")
        self.assertEqual(props["Confidence"]["select"]["name"], "Medium")

    def test_competitor_page_properties_include_ranking_fields(self):
        record = CompetitorSiteRecord(
            url="https://example.com/lp",
            domain="example.com",
            source_title="Example LP",
            structure_type="Ranking",
            rankings=["A", "B", "C", "D", "E"],
            main_cta="無料相談",
            listed_players=["A", "B", "C"],
            direct_competitor=True,
            evidence_snippet="ランキング",
            research_run_id="run-1",
        )

        props = competitor_page_properties(record)

        self.assertEqual(props["Fact"]["title"][0]["text"]["content"], "example.com")
        self.assertEqual(props["Ranking 1"]["rich_text"][0]["text"]["content"], "A")
        self.assertEqual(props["Ranking 5"]["rich_text"][0]["text"]["content"], "E")
        self.assertTrue(props["Direct Competitor"]["checkbox"])


if __name__ == "__main__":
    unittest.main()
