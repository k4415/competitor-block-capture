import json
import tempfile
import unittest
from pathlib import Path

from listing_os.workflows import analyze_serp_snapshot, export_vendor_pack, generate_vendor_brief


class WorkflowTest(unittest.TestCase):
    def test_analyze_serp_snapshot_deduplicates_by_domain_and_scores_results(self):
        snapshot = {
            "genre_id": "hair-transplant",
            "query": "植毛 比較",
            "results": [
                {
                    "rank": 1,
                    "type": "organic",
                    "url": "https://www.example.com/ranking?utm_source=google",
                    "title": "植毛おすすめ比較",
                    "description": "料金・実績・症例で比較",
                },
                {
                    "rank": 3,
                    "type": "paid",
                    "url": "https://example.com/lp?gclid=abc",
                    "title": "植毛クリニック比較",
                    "description": "無料相談 CTA",
                },
                {
                    "rank": 2,
                    "type": "organic",
                    "url": "https://competitor.jp/",
                    "title": "植毛ランキング",
                    "description": "口コミと価格",
                },
            ],
        }

        analysis = analyze_serp_snapshot(snapshot, limit=10)

        self.assertEqual([site["domain"] for site in analysis["competitor_sites"]], ["example.com", "competitor.jp"])
        self.assertGreater(analysis["competitor_sites"][0]["score"], analysis["competitor_sites"][1]["score"])
        self.assertEqual(analysis["stats"]["raw_results"], 3)
        self.assertEqual(analysis["stats"]["unique_domains"], 2)

    def test_generate_vendor_brief_omits_secrets_and_includes_handoff_sections(self):
        analysis = {
            "genre_id": "hair-transplant",
            "query": "植毛 比較",
            "competitor_sites": [
                {
                    "domain": "example.com",
                    "best_rank": 1,
                    "score": 94,
                    "title": "植毛おすすめ比較",
                    "description": "料金・実績・症例で比較",
                    "url": "https://example.com/ranking",
                }
            ],
        }
        offers = [{"name": "Aクリニック", "commission": "承認後 30,000円", "approval_terms": "要確認"}]

        brief = generate_vendor_brief(
            genre_id="hair-transplant",
            genre_name="植毛",
            analysis=analysis,
            offers=offers,
            internal_notes="DATAFORSEO_PASSWORD=secret",
        )

        self.assertIn("# 外注指示パック: 植毛", brief)
        self.assertIn("## 比較LP構成案", brief)
        self.assertIn("## 検収条件", brief)
        self.assertNotIn("secret", brief)
        self.assertNotIn("DATAFORSEO_PASSWORD", brief)

    def test_export_vendor_pack_writes_sanitized_markdown_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "pack"

            written = export_vendor_pack(
                brief_markdown="# Brief\n\nAPI_KEY=secret\n\nPublic line",
                output_dir=out_dir,
                pack_id="hair-transplant-v1",
            )

            brief_text = written["brief_path"].read_text(encoding="utf-8")
            manifest = json.loads(written["manifest_path"].read_text(encoding="utf-8"))

        self.assertNotIn("secret", brief_text)
        self.assertIn("[REDACTED]", brief_text)
        self.assertEqual(manifest["pack_id"], "hair-transplant-v1")
        self.assertEqual(manifest["files"], ["brief.md"])


if __name__ == "__main__":
    unittest.main()
