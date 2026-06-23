import unittest

from research_os.web import JobState, render_index, render_job


class ResearchWebTest(unittest.TestCase):
    def test_index_uses_studio_shell_layout(self):
        html = render_index()

        self.assertIn("app-shell", html)
        self.assertIn("studio-sidebar", html)
        self.assertIn("CMOAI", html)
        self.assertIn("RESEARCH OS", html)
        self.assertIn("step-bar", html)
        self.assertIn("コンテキスト入力", html)
        self.assertIn("リサーチ実行", html)
        self.assertIn("Notion反映", html)
        self.assertIn("studio-card", html)

    def test_queued_job_page_refreshes_to_job_detail(self):
        html = render_job(JobState(job_id="job-1", status="queued", message="queued"))

        self.assertIn('http-equiv="refresh"', html)
        self.assertIn("url=/runs/job-1", html)
        self.assertIn("Status: queued", html)

    def test_done_job_page_does_not_auto_refresh(self):
        html = render_job(JobState(job_id="job-1", status="done", message="完了"))

        self.assertNotIn('http-equiv="refresh"', html)
        self.assertIn("Status: done", html)

    def test_failed_quality_job_shows_inputs_and_no_notion_link(self):
        job = JobState(
            job_id="job-1",
            status="failed",
            message="品質基準未達",
            error="品質基準未達: カテゴリー30件以上",
            result={
                "input_category": "結婚相談",
                "canonical_category": "結婚相談所",
                "competitor_url_count": 3,
                "source_count": 1,
                "quality_status": "failed",
                "notion_created": False,
                "openai_available": False,
                "seed_source_count": 0,
                "competitor_source_count": 1,
                "research_mode": "local_fallback",
                "quality_missing": ["メインプレイヤー3社以上"],
                "next_action": "カテゴリ別seedまたは公式URLを追加してください",
                "row_counts": {"category": 0, "target": 1, "players": 0, "competitor_sites": 1},
            },
        )

        html = render_job(job)

        self.assertIn("入力カテゴリ: 結婚相談", html)
        self.assertIn("正規化カテゴリ: 結婚相談所", html)
        self.assertIn("競合URL数: 3", html)
        self.assertIn("品質判定: failed", html)
        self.assertIn("Notion作成: なし", html)
        self.assertIn("alert-card alert-error", html)
        self.assertIn("metric-grid", html)
        self.assertIn("OpenAI: 未設定", html)
        self.assertIn("seedソース数: 0", html)
        self.assertIn("不足項目: メインプレイヤー3社以上", html)
        self.assertIn("次に直す入力: カテゴリ別seedまたは公式URLを追加してください", html)
        self.assertNotIn("Notionページを開く", html)

    def test_done_job_page_shows_success_card_and_notion_link(self):
        job = JobState(
            job_id="job-2",
            status="done",
            message="完了",
            result={
                "input_category": "結婚相談所",
                "canonical_category": "結婚相談所",
                "competitor_url_count": 3,
                "source_count": 28,
                "quality_status": "passed",
                "notion_created": True,
                "category_page_url": "https://www.notion.so/example",
                "row_counts": {"category": 32, "target": 34, "players": 5, "competitor_sites": 3},
            },
        )

        html = render_job(job)

        self.assertIn("alert-card alert-success", html)
        self.assertIn("Notionページを開く", html)
        self.assertIn("metric-grid", html)
        self.assertIn("row-counts", html)
        self.assertIn("category: 32", html)


if __name__ == "__main__":
    unittest.main()
