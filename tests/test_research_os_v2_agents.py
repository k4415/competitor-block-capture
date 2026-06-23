import unittest

from research_os.models import SourceDocument
from research_os.v2.agents import CategoryResearchAgent, CompetitorSiteResearchAgent, PlayerResearchAgent, TargetResearchAgent


def marriage_docs():
    return [
        SourceDocument(
            "https://example.com/category",
            "結婚相談所カテゴリ調査",
            """
            出会いの方法は自分で検索、カウンセラー紹介、システムによるレコメンド、オフラインイベントに分類される。
            STEP①お見合いでは連絡先交換禁止。STEP②プレ交際では複数交際と新規お見合いが認められる。
            STEP③真剣交際では他の方との交際、新規お見合い、検索システムの利用は停止。
            3カ月ルールではお見合いから成婚まで原則3カ月で意思決定する。
            成婚定義は婚約、結婚意思を固めて退会、結婚前提の真剣交際に分かれる。
            成婚までの期間は入会後約5ヶ月から7ヶ月くらいが多い。
            入会金は銀行振込やクレジットカード、月会費は銀行引き落としやクレジットカードに対応する。
            大手のカウンセラー数は約80人から200人程度、少人数制は20人から40人程度。
            IBJは会員数9万人越え、TMSはSCRUM全体で6.7万人規模、BIUは古い連盟、コネクトシップは相互紹介プラットフォーム。
            比較対象にはマッチングアプリ、婚活パーティー、街コン、知人紹介がある。
            リスクは金銭的損失、時間的損失、強引な成婚誘導への警戒がある。
            """,
        ),
        SourceDocument(
            "https://example.com/target",
            "ターゲット調査",
            """
            結婚相談所は30代がメインのサービスで、次いで20代・40代と需要が存在する。
            20代男性は20代のうちに結婚したい、結婚前提の出会いを探している。マッチングアプリでは結婚は難しいと感じる。
            20代男性の懸念は経済力のない自分は相手にされないのでは、高いお金を払って出会えなかったらどうしよう。
            30代男性はそろそろ本気で結婚を考えたい、早く最短で結婚したい。このまま一人でいいのかと不安。
            30代男性の懸念は魅力的な女性は本当にいるのか、恋愛経験が乏しくても大丈夫か。
            20代女性は30歳までに結婚したい、子どもを複数人授かりたい。マッチングアプリは効率が悪いと感じる。
            20代女性の懸念は誰からも選ばれなかったら、純粋な恋愛ができるのか。
            30代女性は最短距離で結婚したい、子どもがほしい。このまま一人で生きていくのかと不安。
            30代女性の懸念は本当に結婚できるのか、遅かったかもしれない、お金も時間も無駄にならないか。
            共通欲求は本気で結婚したいという強い願望。共通懸念は金銭的損失、時間的損失、会員の質、強引な成婚誘導。
            入会者の多くは他の婚活サービスを経験済みで、20代から30代はマッチングアプリ経験後に相談所へ入会する。
            """,
        ),
        SourceDocument(
            "https://www.zwei.com/",
            "ツヴァイ公式",
            """
            ツヴァイは紹介書、価値観マッチング、条件検索、店舗でのサポートを提供する。
            特徴は全国店舗、IBJ会員との出会い、専任カウンセラー。
            メリットは効率的に結婚前提の相手を探せて、活動中に相談できる安心感があること。
            実績は会員数、成婚退会者、利用者の声を掲載。
            権威性はIBJグループとして運営される企業信頼。
            オファーは無料相談、入会初期費用、月会費、成婚料のプラン。
            リスク・制約は活動費用、地域、条件によって紹介数が変わること。
            会社情報は株式会社ZWEIが運営。
            """,
        ),
        SourceDocument(
            "https://lp.example.com/ranking",
            "比較ランキングLP",
            """
            1位 ツヴァイ 公式サイトを見る 無料相談
            2位 サンマリエ 資料請求
            3位 オーネット 無料診断
            4位 IBJメンバーズ 来店予約
            5位 ゼクシィ縁結びエージェント 無料相談
            見出し: 結婚相談所おすすめランキング
            比較軸: 料金、会員数、サポート、成婚実績
            画像内テキスト: 今なら無料相談受付中
            証拠表現: 会員数、成婚実績、口コミ
            訴求パターン: 短期成婚、安心サポート、料金比較
            """,
        ),
    ]


class ResearchV2AgentTest(unittest.TestCase):
    def test_category_agent_extracts_minimum_marriage_agency_coverage(self):
        facts = CategoryResearchAgent().extract(marriage_docs(), category_name="結婚相談所", research_run_id="run-v2")
        by_major = {fact.major_category for fact in facts}
        fact_text = "\n".join(fact.fact for fact in facts)

        self.assertGreaterEqual(len(facts), 30)
        self.assertGreaterEqual(by_major, {"出会いの方法", "利用ステップ", "交際ルール", "成婚定義", "成婚期間", "連盟・会員基盤"})
        self.assertIn("3カ月", fact_text)
        self.assertIn("IBJ", fact_text)

    def test_target_agent_extracts_segments_and_desires_concerns(self):
        facts = TargetResearchAgent().extract(marriage_docs(), category_name="結婚相談所", research_run_id="run-v2")
        segments = {fact.segment for fact in facts}
        by_major = {fact.major_category for fact in facts}

        self.assertGreaterEqual(len(facts), 30)
        self.assertGreaterEqual(segments, {"20代男性", "30代男性", "20代女性", "30代女性", "共通"})
        self.assertGreaterEqual(by_major, {"デモグラ", "婚活歴", "欲求", "状態", "懸念", "比較対象"})

    def test_player_agent_builds_seven_section_record(self):
        players = PlayerResearchAgent().extract(marriage_docs(), research_run_id="run-v2")
        zwei = next(player for player in players if player.player_name == "ツヴァイ")

        self.assertEqual(zwei.official_url, "https://www.zwei.com/")
        for section in ["特徴", "メリット", "実績", "権威性", "オファー", "リスク・制約", "会社情報"]:
            self.assertIn(section, zwei.sections)
            self.assertTrue(zwei.sections[section])

    def test_competitor_agent_structures_site_without_full_text_dump(self):
        competitors = CompetitorSiteResearchAgent().extract(marriage_docs(), competitor_urls=["https://lp.example.com/ranking"], research_run_id="run-v2")
        record = competitors[0]

        self.assertEqual(record.rankings[:5], ["ツヴァイ", "サンマリエ", "オーネット", "IBJメンバーズ", "ゼクシィ縁結びエージェント"])
        self.assertIn("無料相談", record.main_cta)
        self.assertIn("今なら無料相談受付中", record.image_text_summary)
        self.assertLess(len(record.structured_body), 2500)

    def test_competitor_agent_uses_only_input_competitor_urls(self):
        competitors = CompetitorSiteResearchAgent().extract(
            marriage_docs(),
            competitor_urls=["https://lp.example.com/ranking"],
            research_run_id="run-v2",
        )

        self.assertEqual([record.url for record in competitors], ["https://lp.example.com/ranking"])

    def test_competitor_agent_returns_empty_without_input_urls(self):
        competitors = CompetitorSiteResearchAgent().extract(marriage_docs(), competitor_urls=[], research_run_id="run-v2")

        self.assertEqual(competitors, [])


if __name__ == "__main__":
    unittest.main()
