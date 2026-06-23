import unittest

from research_os.extractors import HeuristicExtractor
from research_os.models import SourceDocument


class CompetitorExtractorTest(unittest.TestCase):
    def test_competitor_url_becomes_one_page_record_with_rankings_and_cta(self):
        doc = SourceDocument(
            url="https://soudanjo-hikaku.com/",
            title="相談所比較.com",
            text="""
            失敗しない結婚相談所ランキング。おすすめポイント。
            1位 ツヴァイ 成婚率No.1 会員数11.2万人 完全無料マッチング無料体験。
            2位 サンマリエ 専任カウンセラー。
            3位 フィオーレ。
            4位 パートナーエージェント。
            5位 IBJメンバーズ。
            公式サイトを見る。無料診断。
            """,
        )

        record = HeuristicExtractor().extract_competitor_site(doc, research_run_id="run-1", direct=True)

        self.assertEqual(record.url, "https://soudanjo-hikaku.com/")
        self.assertEqual(record.domain, "soudanjo-hikaku.com")
        self.assertTrue(record.direct_competitor)
        self.assertEqual(record.rankings[0], "ツヴァイ")
        self.assertEqual(record.rankings[4], "IBJメンバーズ")
        self.assertIn("無料", record.main_cta)

    def test_player_extraction_handles_result_patterns_without_capture_groups(self):
        doc = SourceDocument(
            url="https://example.com",
            title="Example",
            text="ツヴァイは成婚までのサポートがある。無料相談もある。",
        )

        players = HeuristicExtractor().extract_players([doc], research_run_id="run-1")

        self.assertEqual(players[0].player_name, "ツヴァイ")
        self.assertIn("成婚", players[0].results)


if __name__ == "__main__":
    unittest.main()
