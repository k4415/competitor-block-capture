import unittest

from listing_os.notion.schema import build_database_specs, build_relation_update_properties, without_relation_properties


class NotionSchemaTest(unittest.TestCase):
    def test_build_database_specs_contains_v1_relation_tables(self):
        specs = build_database_specs(parent_page_id="de02e0f0cbe8824ca79201a3b390bd43")
        names = {spec["key"]: spec["title"] for spec in specs}

        self.assertEqual(names["genres"], "ジャンル")
        self.assertEqual(names["serp_snapshots"], "SERPスナップショット")
        self.assertEqual(names["vendor_briefs"], "外注指示パック")
        self.assertEqual(len(specs), 10)

    def test_database_spec_uses_current_notion_create_database_shape(self):
        specs = build_database_specs(parent_page_id="de02e0f0cbe8824ca79201a3b390bd43")
        genre = next(spec for spec in specs if spec["key"] == "genres")

        self.assertEqual(genre["request"]["parent"]["type"], "page_id")
        self.assertIn("initial_data_source", genre["request"])
        self.assertIn("properties", genre["request"]["initial_data_source"])
        self.assertEqual(genre["request"]["is_inline"], False)

    def test_relation_properties_are_added_after_data_sources_exist(self):
        specs = build_database_specs(parent_page_id="de02e0f0cbe8824ca79201a3b390bd43")
        queries = next(spec for spec in specs if spec["key"] == "queries")
        stripped = without_relation_properties(queries["request"])

        self.assertNotIn("Genre", stripped["initial_data_source"]["properties"])

        updates = build_relation_update_properties(
            queries["request"],
            data_source_ids={"genres": "genre-ds-id"},
        )

        self.assertEqual(updates["Genre"], {"relation": {"data_source_id": "genre-ds-id", "single_property": {}}})


if __name__ == "__main__":
    unittest.main()
