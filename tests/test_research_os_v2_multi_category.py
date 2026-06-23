import unittest

from research_os.models import SourceDocument
from research_os.v2.agents import CategoryResearchAgent, PlayerResearchAgent, TargetResearchAgent
from research_os.v2.openai_research import _prompt
from research_os.v2.profiles import resolve_genre_profile
from research_os.v2.quality import QualityGateError, evaluate_v2_quality, validate_v2_quality
from research_os.v2.runner import ResearchV2Request, collect_v2_research_bundle
from research_os.v2.seeds import seed_documents_for_category
from research_os.v2.models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Bundle, ResearchV2Fact


PROFILE_EXPECTATIONS = {
    "金買取": ("purchase", "金買取"),
    "オリパ": ("commerce", "オリパ"),
    "植毛": ("medical", "植毛"),
    "いびき治療": ("medical", "いびき治療"),
    "マウスピース矯正": ("medical", "マウスピース矯正"),
}


def generic_docs(category_name: str) -> list[SourceDocument]:
    profile = resolve_genre_profile(category_name)
    profile_topic_text = "。".join(f"{topic}は{category_name}の比較で確認する" for topic in profile.category_topics)
    return [
        SourceDocument(
            f"https://example.com/{category_name}/guide",
            f"{category_name}公式ガイド",
            f"""
            {category_name}は比較検討型の商品・サービスで、サービス/商品の定義を理解してから申し込む。
            利用・購入ステップは情報収集、比較、無料相談、見積もり、申込、契約、利用開始に分かれる。
            料金体系は初期費用、月額費用、成果報酬、手数料、オプション費用、送料、キャンセル条件を確認する。
            比較対象は専門サービス、店舗、オンラインサービス、セルフ対応、他社サービスである。
            主要プレイヤーは大手企業、専門クリニック、専門店、オンライン事業者、比較サイト掲載企業である。
            意思決定基準は価格、実績、口コミ、サポート、保証、利便性、信頼性である。
            リスク・注意点は追加費用、期待外れ、品質差、返金条件、トラブル対応、個人情報の扱いである。
            法規制・広告表現制約は景表法、特商法、業法、医療広告ガイドライン、薬機法の確認が必要である。
            {profile_topic_text}
            """,
        ),
        SourceDocument(
            f"https://example.com/{category_name}/target",
            f"{category_name}ユーザー調査",
            f"""
            {category_name}のデモグラは20代、30代、40代、50代以上、男性、女性、共通に分かれる。
            利用前状態は悩みが顕在化し、複数サービスを比較し、失敗したくない状態である。
            欲求は短期間で解決したい、納得できる価格で利用したい、信頼できる会社を選びたいことである。
            懸念は費用が無駄にならないか、効果が出るか、悪質業者ではないか、手続きが面倒ではないかである。
            ビリーフは専門家や大手なら安心、口コミや実績が多いほど信頼できる、安すぎるサービスは不安という認識である。
            比較対象は専門サービス、店舗、オンラインサービス、セルフ対応、既存の代替手段である。
            購入/申込トリガーは無料相談、キャンペーン、診断、査定、症例、口コミ、ランキングである。
            意思決定基準は価格、実績、口コミ、保証、サポート、スピード、近さ、手軽さである。
            """,
        ),
        SourceDocument(
            f"https://player.example.com/{category_name}/",
            f"{category_name}公式",
            f"""
            {category_name}スターは{category_name}サービス。
            特徴はオンライン対応、専門スタッフ、明確な料金、比較しやすいプラン。
            メリットは手間を減らし、安心して申し込みしやすいこと。
            実績は利用者数、口コミ、事例、満足度を掲載。
            権威性は専門家監修、許認可、運営会社の信頼性。
            オファーは無料相談、無料診断、無料査定、キャンペーン、資料請求。
            リスク・制約は条件、費用、地域、在庫、適応可否によって結果が変わること。
            会社情報は株式会社サンプルが運営。
            """,
        ),
    ]


class ResearchV2MultiCategoryTest(unittest.TestCase):
    def test_priority_categories_resolve_to_known_profiles(self):
        for raw_name, (expected_type, canonical_name) in PROFILE_EXPECTATIONS.items():
            with self.subTest(raw_name=raw_name):
                profile = resolve_genre_profile(raw_name)

                self.assertTrue(profile.known)
                self.assertEqual(profile.category_type, expected_type)
                self.assertEqual(profile.canonical_name, canonical_name)
                self.assertGreaterEqual(profile.thresholds.category_facts, 12)
                self.assertGreaterEqual(profile.thresholds.target_facts, 10)

    def test_generic_agents_extract_cross_category_core_facts(self):
        facts = CategoryResearchAgent().extract(generic_docs("金買取"), category_name="金買取", research_run_id="run-v2")
        by_major = {fact.major_category for fact in facts}

        self.assertGreaterEqual(len(facts), 8)
        self.assertGreaterEqual(
            by_major,
            {"サービス/商品の定義", "利用・購入ステップ", "料金体系", "比較対象", "主要プレイヤー", "意思決定基準", "リスク・注意点", "法規制・広告表現制約"},
        )

    def test_generic_target_agent_extracts_core_segments(self):
        facts = TargetResearchAgent().extract(generic_docs("オリパ"), category_name="オリパ", research_run_id="run-v2")
        by_major = {fact.major_category for fact in facts}
        segments = {fact.segment for fact in facts}

        self.assertGreaterEqual(len(facts), 8)
        self.assertGreaterEqual(by_major, {"デモグラ", "利用前状態", "欲求", "懸念", "ビリーフ", "比較対象", "購入/申込トリガー", "意思決定基準"})
        self.assertIn("共通", segments)

    def test_medical_categories_require_risk_and_regulation_facts(self):
        for category_name in ["植毛", "いびき治療", "マウスピース矯正"]:
            with self.subTest(category_name=category_name):
                facts = CategoryResearchAgent().extract(generic_docs(category_name), category_name=category_name, research_run_id="run-v2")
                by_major = {fact.major_category for fact in facts}

                self.assertIn("リスク・注意点", by_major)
                self.assertIn("法規制・広告表現制約", by_major)

    def test_profile_quality_gate_requires_profile_categories(self):
        category_facts = CategoryResearchAgent().extract(generic_docs("金買取"), category_name="金買取", research_run_id="run-v2")
        target_facts = TargetResearchAgent().extract(generic_docs("金買取"), category_name="金買取", research_run_id="run-v2")
        players = PlayerResearchAgent().extract(generic_docs("金買取"), research_run_id="run-v2")
        bundle = ResearchV2Bundle(category_facts=category_facts, target_facts=target_facts, players=players, competitors=[], source_count=3)

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("金買取", bundle)

        self.assertIn("競合サイト1件以上", str(raised.exception))

    def test_priority_profile_quality_gate_passes_with_required_facts_and_counts(self):
        for category_name in PROFILE_EXPECTATIONS:
            with self.subTest(category_name=category_name):
                category_facts = CategoryResearchAgent().extract(generic_docs(category_name), category_name=category_name, research_run_id="run-v2")
                target_facts = TargetResearchAgent().extract(generic_docs(category_name), category_name=category_name, research_run_id="run-v2")
                bundle = ResearchV2Bundle(
                    category_facts=category_facts,
                    target_facts=target_facts,
                    players=[_player(index) for index in range(3)],
                    competitors=[_competitor()],
                    source_count=12,
                )

                report = validate_v2_quality(category_name, bundle)

                self.assertEqual(report.status, "passed")

    def test_medical_quality_gate_requires_risk_and_regulation_categories(self):
        bundle = ResearchV2Bundle(
            category_facts=[_fact(index, "サービス/商品の定義") for index in range(12)],
            target_facts=[_fact(index, "欲求") for index in range(10)],
            players=[_player(index) for index in range(3)],
            competitors=[_competitor()],
            source_count=12,
        )

        with self.assertRaises(QualityGateError) as raised:
            validate_v2_quality("植毛", bundle)

        self.assertIn("必須カテゴリー: リスク・注意点", str(raised.exception))
        self.assertIn("必須カテゴリー: 法規制・広告表現制約", str(raised.exception))

    def test_openai_prompt_uses_profile_topics_for_non_marriage_category(self):
        class Request:
            category_name = "植毛"
            depth = "standard"
            memo = "医療系比較リス"

        prompt = _prompt(Request(), generic_docs("植毛"), "カテゴリーリサーチ")

        self.assertIn("正規カテゴリ: 植毛", prompt)
        self.assertIn("カテゴリ種別: medical", prompt)
        self.assertIn("FUE/FUT", prompt)
        self.assertIn("医療広告ガイドライン", prompt)
        self.assertIn("ターゲットセグメント", prompt)

    def test_priority_seed_documents_include_mouthpiece_sources_and_players(self):
        docs = seed_documents_for_category("マウスピース矯正")
        text = "\n".join(doc.text for doc in docs)
        titles = [doc.title for doc in docs]

        self.assertGreaterEqual(len(docs), 5)
        self.assertIn("マウスピース矯正 カテゴリー基礎", titles)
        self.assertIn("矯正方式", text)
        self.assertIn("適応症例", text)
        self.assertIn("医療広告制約", text)
        self.assertIn("リスク・注意点", text)
        self.assertIn("法規制・広告表現制約", text)
        self.assertIn("インビザライン", text)
        self.assertIn("キレイライン", text)
        self.assertIn("Oh my teeth", text)

    def test_mouthpiece_profile_passes_quality_without_openai_from_fallback_sources(self):
        competitor_url = "https://example.com/mouthpiece-ranking"
        docs = seed_documents_for_category("マウスピース矯正") + [
            SourceDocument(
                competitor_url,
                "マウスピース矯正 比較LP",
                """
                1位 インビザライン。2位 キレイライン。3位 Oh my teeth。
                CTAは無料相談。比較軸: 費用、期間、症例、通院頻度。
                証拠表現: 歯科医師監修、症例掲載。画像内主要文言: 透明で目立ちにくい。
                """,
            )
        ]
        request = ResearchV2Request(
            category_name="マウスピース矯正",
            competitor_urls=[competitor_url],
            parent_page_id="parent",
            use_openai=False,
        )

        bundle = collect_v2_research_bundle(request, source_documents=docs)
        report = evaluate_v2_quality("マウスピース矯正", bundle, expected_competitors=1)

        self.assertTrue(report.passed, report.message())
        self.assertGreaterEqual(len(bundle.category_facts), 12)
        self.assertGreaterEqual(len(bundle.target_facts), 10)
        self.assertGreaterEqual(len(bundle.players), 3)
        self.assertGreaterEqual(len(bundle.competitors), 1)
        self.assertGreaterEqual(bundle.source_count, 3)
        self.assertEqual(bundle.diagnostics["research_mode"], "provided_sources")
        self.assertFalse(bundle.diagnostics["openai_available"])


def _fact(index: int, major_category: str) -> ResearchV2Fact:
    return ResearchV2Fact(
        fact=f"{major_category} fact {index}",
        major_category=major_category,
        sub_category="テスト",
        segment="共通",
        source_url=f"https://example.com/fact-{index}",
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


def _competitor() -> CompetitorSiteV2Record:
    return CompetitorSiteV2Record(
        url="https://example.com/ranking",
        domain="example.com",
        source_title="sample",
        evidence_snippet="sample",
        confidence="高",
        verification_status="検証済み",
        research_run_id="run-v2",
        structure_type="ランキングLP",
        rankings=["サービスA"],
        main_cta="無料相談",
        listed_players=["サービスA"],
        image_text_summary="sample",
        structured_body="sample",
        direct_competitor=True,
    )


if __name__ == "__main__":
    unittest.main()
