import unittest

from research_os.models import CompetitorSiteRecord, PlayerRecord, ResearchBundle, ResearchFact
from research_os.notion_workspace import create_research_workspace


class FakeNotionClient:
    def __init__(self):
        self.created_child_pages = []
        self.created_databases = []
        self.created_pages = []

    def create_child_page(self, parent_page_id, title, children=None):
        page = {"id": f"page-{len(self.created_child_pages) + 1}", "url": f"https://notion.test/page-{len(self.created_child_pages) + 1}"}
        self.created_child_pages.append({"parent_page_id": parent_page_id, "title": title, "children": children or []})
        return page

    def create_database(self, payload):
        database_id = f"db-{len(self.created_databases) + 1}"
        data_source_id = f"ds-{len(self.created_databases) + 1}"
        self.created_databases.append(payload)
        return {"id": database_id, "data_sources": [{"id": data_source_id}]}

    def create_page(self, data_source_id, properties, children=None):
        page = {"id": f"row-{len(self.created_pages) + 1}"}
        self.created_pages.append({"data_source_id": data_source_id, "properties": properties, "children": children or []})
        return page


class ResearchWorkspaceTest(unittest.TestCase):
    def test_create_research_workspace_builds_page_four_dbs_and_rows(self):
        bundle = ResearchBundle(
            category_facts=[
                ResearchFact("category", "無料相談が初回接点", "Step", "https://example.com", "Example", "無料相談", "High", "run-1")
            ],
            target_facts=[
                ResearchFact("target", "料金に不安がある", "Concern", "https://example.com", "Example", "料金", "Medium", "run-1")
            ],
            players=[
                PlayerRecord("ツヴァイ", "https://example.com", "Example", "ツヴァイ", "run-1", members="11万人")
            ],
            competitors=[
                CompetitorSiteRecord(
                    url="https://lp.example.com",
                    domain="lp.example.com",
                    source_title="LP",
                    structure_type="Ranking",
                    rankings=["ツヴァイ", "サンマリエ", "", "", ""],
                    main_cta="無料相談",
                    listed_players=["ツヴァイ", "サンマリエ"],
                    direct_competitor=True,
                    evidence_snippet="ランキング",
                    research_run_id="run-1",
                    full_transcript_summary="要約",
                )
            ],
        )
        fake = FakeNotionClient()

        result = create_research_workspace(
            notion=fake,
            parent_page_id="parent",
            category_name="結婚相談所",
            memo="比較リスティング",
            bundle=bundle,
            research_run_id="run-1",
        )

        self.assertEqual(fake.created_child_pages[0]["title"], "結婚相談所 比較リスティング調査")
        self.assertEqual(len(fake.created_databases), 4)
        self.assertEqual(len(fake.created_pages), 4)
        self.assertEqual(result["category_page_url"], "https://notion.test/page-1")
        self.assertEqual(result["row_counts"]["competitor_sites"], 1)


if __name__ == "__main__":
    unittest.main()
