import unittest

from research_os.v2.models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Bundle, ResearchV2Fact
from research_os.v2.notion_workspace import create_v2_research_workspace
from research_os.v2.runner import ResearchV2Request, collect_v2_research_bundle


class FakeNotionClient:
    def __init__(self):
        self.trashed_pages = []
        self.created_child_pages = []
        self.created_databases = []
        self.created_pages = []

    def trash_page(self, page_id):
        self.trashed_pages.append(page_id)
        return {"id": page_id, "archived": True}

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


class AlreadyArchivedNotionClient(FakeNotionClient):
    def trash_page(self, page_id):
        self.trashed_pages.append(page_id)
        raise RuntimeError(
            "Notion API PATCH /pages/old-page failed with HTTP 400: "
            "{\"message\":\"Can't edit block that is archived. You must unarchive the block before editing.\"}"
        )


class ResearchV2WorkspaceTest(unittest.TestCase):
    def test_create_v2_workspace_replaces_v1_and_writes_japanese_properties(self):
        bundle = ResearchV2Bundle(
            category_facts=[
                ResearchV2Fact("結婚相談所には3STEPがある", "利用ステップ", "3STEP", "共通", "https://example.com", "Example", "3STEP", "高", "検証済み", "run-v2")
            ],
            target_facts=[
                ResearchV2Fact("30代男性は最短で結婚したい", "欲求", "30代男性", "30代男性", "https://example.com", "Example", "最短で結婚", "中", "検証済み", "run-v2")
            ],
            players=[
                PlayerV2Record(
                    player_name="ツヴァイ",
                    official_url="https://www.zwei.com/",
                    source_url="https://www.zwei.com/",
                    source_title="ツヴァイ",
                    evidence_snippet="無料相談",
                    confidence="高",
                    verification_status="検証済み",
                    research_run_id="run-v2",
                    sections={"特徴": ["紹介書"], "メリット": ["相談できる"], "実績": ["会員数"], "権威性": ["IBJ"], "オファー": ["無料相談"], "リスク・制約": ["費用"], "会社情報": ["株式会社ZWEI"]},
                )
            ],
            competitors=[
                CompetitorSiteV2Record(
                    url="https://lp.example.com/ranking",
                    domain="lp.example.com",
                    source_title="LP",
                    evidence_snippet="1位 ツヴァイ",
                    confidence="高",
                    verification_status="検証済み",
                    research_run_id="run-v2",
                    structure_type="ランキングLP",
                    rankings=["ツヴァイ", "サンマリエ", "オーネット", "IBJメンバーズ", "ゼクシィ縁結びエージェント"],
                    main_cta="無料相談",
                    listed_players=["ツヴァイ", "サンマリエ"],
                    image_text_summary="今なら無料相談受付中",
                    structured_body="## 構成順\n1. FV\n",
                    direct_competitor=True,
                )
            ],
            source_count=6,
            failed_urls=["https://failed.example.com"],
        )
        fake = FakeNotionClient()

        result = create_v2_research_workspace(
            notion=fake,
            parent_page_id="parent",
            category_name="結婚相談所",
            memo="V2",
            bundle=bundle,
            research_run_id="run-v2",
            replace_page_ids=["old-page"],
        )

        self.assertEqual(fake.trashed_pages, ["old-page"])
        self.assertEqual(fake.created_child_pages[0]["title"], "結婚相談所 比較リスティング調査 V2")
        self.assertEqual(len(fake.created_databases), 4)
        self.assertEqual(fake.created_pages[0]["properties"]["事実"]["title"][0]["text"]["content"], "結婚相談所には3STEPがある")
        self.assertEqual(result["source_count"], 6)
        self.assertEqual(result["needs_review_count"], 0)

    def test_create_v2_workspace_skips_already_archived_v1_page(self):
        bundle = ResearchV2Bundle(category_facts=[], target_facts=[], players=[], competitors=[], source_count=0)
        fake = AlreadyArchivedNotionClient()

        result = create_v2_research_workspace(
            notion=fake,
            parent_page_id="parent",
            category_name="結婚相談所",
            memo="V2",
            bundle=bundle,
            research_run_id="run-v2",
            replace_page_ids=["old-page"],
        )

        self.assertEqual(fake.trashed_pages, ["old-page"])
        self.assertEqual(result["skipped_v1_pages"], ["old-page"])
        self.assertEqual(fake.created_child_pages[0]["title"], "結婚相談所 比較リスティング調査 V2")

    def test_collect_v2_bundle_uses_openai_client_when_available(self):
        class FakeOpenAIClient:
            def __init__(self):
                self.called_with = None

            def available(self):
                return True

            def research(self, request, source_documents=None):
                self.called_with = (request, source_documents)
                return ResearchV2Bundle(category_facts=[], target_facts=[], players=[], competitors=[], source_count=0)

        client = FakeOpenAIClient()
        request = ResearchV2Request(category_name="マウスピース矯正", competitor_urls=[], parent_page_id="parent", use_openai=True)

        bundle = collect_v2_research_bundle(request, openai_client=client)

        self.assertEqual(bundle.counts(), {"category_facts": 0, "target_facts": 0, "players": 0, "competitors": 0})
        self.assertEqual(client.called_with[0].category_name, "マウスピース矯正")
        self.assertGreaterEqual(len(client.called_with[1]), 5)
        self.assertTrue(bundle.diagnostics["openai_available"])
        self.assertEqual(bundle.diagnostics["research_mode"], "openai")
        self.assertGreaterEqual(bundle.diagnostics["seed_source_count"], 5)


if __name__ == "__main__":
    unittest.main()
