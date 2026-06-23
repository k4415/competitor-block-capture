import unittest

from research_os.v2.models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Bundle, ResearchV2Fact
from research_os.v2.profiles import resolve_genre_profile
from research_os.v2.quality import QualityGateError, validate_v2_quality
from research_os.v2.seeds import seed_documents_for_category


class ResearchV2QualityTest(unittest.TestCase):
    def test_marriage_agency_profile_normalizes_aliases(self):
        canonical_names = {
            resolve_genre_profile("結婚相談所").canonical_name,
            resolve_genre_profile("結婚相談").canonical_name,
            resolve_genre_profile("結婚相談所 比較リスティング").canonical_name,
            resolve_genre_profile("婚活相談所").canonical_name,
        }

        self.assertEqual(canonical_names, {"結婚相談所"})

    def test_marriage_agency_seed_matches_category_variants(self):
        self.assertGreaterEqual(len(seed_documents_for_category("結婚相談所 比較リスティング")), 9)
        self.assertGreaterEqual(len(seed_documents_for_category("結婚相談所の比較")), 9)
        self.assertGreaterEqual(len(seed_documents_for_category("結婚相談")), 9)

    def test_marriage_agency_quality_gate_rejects_too_shallow_bundle(self):
        bundle = ResearchV2Bundle(category_facts=[], target_facts=[], players=[], competitors=[], source_count=1)

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("結婚相談所 比較リスティング", bundle)

        message = str(raised.exception)
        self.assertIn("品質基準未達", message)
        self.assertIn("カテゴリー30件以上", message)
        self.assertIn("現在 category=0", message)

    def test_generic_quality_gate_rejects_empty_bundle(self):
        bundle = ResearchV2Bundle(category_facts=[], target_facts=[], players=[], competitors=[], source_count=0)

        with self.assertRaises(QualityGateError):
            validate_v2_quality("未知カテゴリ", bundle)

    def test_quality_gate_rejects_shallow_bundle_for_any_category(self):
        bundle = ResearchV2Bundle(
            category_facts=[],
            target_facts=[
                ResearchV2Fact(
                    fact="薄いターゲット情報",
                    major_category="欲求",
                    sub_category="仮",
                    segment="共通",
                    source_url="https://example.com/target",
                    source_title="sample",
                    evidence_snippet="sample",
                    confidence="中",
                    verification_status="検証済み",
                    research_run_id="run-v2",
                )
            ],
            players=[],
            competitors=[
                CompetitorSiteV2Record(
                    url="https://example.com/ranking",
                    domain="example.com",
                    source_title="sample",
                    evidence_snippet="sample",
                    confidence="中",
                    verification_status="検証済み",
                    research_run_id="run-v2",
                    structure_type="比較LP",
                    rankings=[""],
                    main_cta="",
                    listed_players=[],
                    image_text_summary="",
                    structured_body="sample",
                    direct_competitor=True,
                )
            ],
            source_count=1,
        )

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("未知カテゴリ", bundle)

        self.assertIn("品質基準未達", str(raised.exception))
        self.assertIn("現在 category=0", str(raised.exception))

    def test_quality_gate_does_not_count_failed_competitor_records(self):
        bundle = ResearchV2Bundle(
            category_facts=[_fact(index, "利用ステップ") for index in range(30)],
            target_facts=[_fact(index, "欲求") for index in range(30)],
            players=[_player(index) for index in range(5)],
            competitors=[_competitor("取得失敗")],
            source_count=40,
        )

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("結婚相談所", bundle)

        self.assertIn("競合サイト1件以上", str(raised.exception))

    def test_quality_gate_can_require_input_competitor_url_count(self):
        bundle = ResearchV2Bundle(
            category_facts=[_fact(index, "利用ステップ") for index in range(30)],
            target_facts=[_fact(index, "欲求") for index in range(30)],
            players=[_player(index) for index in range(5)],
            competitors=[_competitor("検証済み")],
            source_count=40,
        )

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("結婚相談所", bundle, expected_competitors=3)

        self.assertIn("競合サイト3件以上", str(raised.exception))


def _fact(index: int, major_category: str) -> ResearchV2Fact:
    return ResearchV2Fact(
        fact=f"fact {index}",
        major_category=major_category,
        sub_category="テスト",
        segment="共通",
        source_url=f"https://example.com/{index}",
        source_title="sample",
        evidence_snippet="sample",
        confidence="高",
        verification_status="検証済み",
        research_run_id="run-v2",
    )


def _player(index: int) -> PlayerV2Record:
    return PlayerV2Record(
        player_name=f"プレイヤー{index}",
        official_url=f"https://player{index}.example.com/",
        source_url=f"https://player{index}.example.com/",
        source_title="sample",
        evidence_snippet="sample",
        confidence="高",
        verification_status="検証済み",
        research_run_id="run-v2",
        sections={"特徴": ["特徴"], "メリット": ["メリット"], "実績": ["実績"], "権威性": ["権威性"], "オファー": ["オファー"], "リスク・制約": ["リスク"], "会社情報": ["会社"]},
    )


def _competitor(verification_status: str) -> CompetitorSiteV2Record:
    return CompetitorSiteV2Record(
        url="https://example.com/ranking",
        domain="example.com",
        source_title="sample",
        evidence_snippet="sample",
        confidence="高",
        verification_status=verification_status,
        research_run_id="run-v2",
        structure_type="ランキングLP",
        rankings=["ツヴァイ"],
        main_cta="無料相談",
        listed_players=["ツヴァイ"],
        image_text_summary="sample",
        structured_body="sample",
        direct_competitor=True,
    )


if __name__ == "__main__":
    unittest.main()
