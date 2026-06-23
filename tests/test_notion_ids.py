import unittest

from listing_os.notion.client import NotionClient
from listing_os.notion.ids import normalize_notion_id


class NotionIdTest(unittest.TestCase):
    def test_normalize_notion_url_extracts_hyphenated_page_id(self):
        value = "https://www.notion.so/36c2e0f0cbe88085a378cb7324dc3909?pvs=4"

        self.assertEqual(normalize_notion_id(value), "36c2e0f0-cbe8-8085-a378-cb7324dc3909")

    def test_normalize_slug_url_extracts_last_32_hex_chars(self):
        value = "https://www.notion.so/CMOAI-v9-0-de02e0f0cbe8824ca79201a3b390bd43?source=copy_link"

        self.assertEqual(normalize_notion_id(value), "de02e0f0-cbe8-824c-a792-01a3b390bd43")

    def test_create_child_page_normalizes_parent_url_before_request(self):
        class CapturingClient(NotionClient):
            def __init__(self):
                super().__init__("token")
                self.payload = None

            def _request(self, method, path, payload):
                self.payload = payload
                return {"id": "new-page", "url": "https://notion.test/new-page"}

        client = CapturingClient()
        client.create_child_page("https://www.notion.so/36c2e0f0cbe88085a378cb7324dc3909", "Test")

        self.assertEqual(client.payload["parent"]["page_id"], "36c2e0f0-cbe8-8085-a378-cb7324dc3909")


if __name__ == "__main__":
    unittest.main()
