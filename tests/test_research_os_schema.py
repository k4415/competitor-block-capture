import unittest

from research_os.notion_schema import build_research_database_specs


class ResearchSchemaTest(unittest.TestCase):
    def test_build_research_database_specs_creates_four_inline_databases(self):
        specs = build_research_database_specs(parent_page_id="genre-page-id")
        titles = [spec.title for spec in specs]

        self.assertEqual(
            titles,
            ["カテゴリーリサーチ", "ターゲットリサーチ", "メインプレイヤーリサーチ", "競合比較サイトリサーチ"],
        )
        self.assertTrue(all(spec.request["is_inline"] for spec in specs))

    def test_common_fact_properties_are_present(self):
        specs = build_research_database_specs(parent_page_id="genre-page-id")
        required = {
            "Fact",
            "Category",
            "Source URL",
            "Source Title",
            "Evidence Snippet",
            "Confidence",
            "Extracted At",
            "Research Run ID",
        }

        for spec in specs:
            props = spec.request["initial_data_source"]["properties"]
            self.assertTrue(required.issubset(set(props)), spec.title)

    def test_competitor_site_schema_has_ranking_and_cta_fields(self):
        competitor = next(spec for spec in build_research_database_specs("genre-page-id") if spec.key == "competitor_sites")
        props = competitor.request["initial_data_source"]["properties"]

        for name in ["URL", "Domain", "Structure Type", "Ranking 1", "Ranking 5", "Main CTA", "Listed Players", "Direct Competitor"]:
            self.assertIn(name, props)


if __name__ == "__main__":
    unittest.main()
