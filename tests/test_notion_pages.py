import unittest

from listing_os.notion.pages import (
    build_competitor_properties,
    build_genre_properties,
    markdown_to_paragraph_blocks,
)


class NotionPagePayloadTest(unittest.TestCase):
    def test_build_genre_properties_uses_title_and_select_values(self):
        props = build_genre_properties(genre_id="hair-transplant", genre_name="植毛")

        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "植毛")
        self.assertEqual(props["Status"]["select"]["name"], "Researching")
        self.assertIn("hair-transplant", props["Decision Log"]["rich_text"][0]["text"]["content"])

    def test_build_competitor_properties_links_genre_and_snapshot(self):
        props = build_competitor_properties(
            site={
                "domain": "example.com",
                "url": "https://example.com",
                "best_rank": 1,
                "score": 98,
                "type": "mixed",
                "title": "比較サイト",
                "description": "料金と口コミ",
            },
            genre_page_id="genre-page",
            snapshot_page_id="snapshot-page",
        )

        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "example.com")
        self.assertEqual(props["Genre"]["relation"], [{"id": "genre-page"}])
        self.assertEqual(props["Snapshot"]["relation"], [{"id": "snapshot-page"}])

    def test_markdown_to_paragraph_blocks_splits_long_text(self):
        blocks = markdown_to_paragraph_blocks("a" * 2500, chunk_size=1000)

        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["type"], "paragraph")
        self.assertEqual(len(blocks[0]["paragraph"]["rich_text"][0]["text"]["content"]), 1000)


if __name__ == "__main__":
    unittest.main()
