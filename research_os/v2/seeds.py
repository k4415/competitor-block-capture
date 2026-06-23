from __future__ import annotations

from research_os.models import SourceDocument

from .profiles import GenreProfile, resolve_genre_profile


def seed_documents_for_category(category_name: str) -> list[SourceDocument]:
    profile = resolve_genre_profile(category_name)
    if profile.key == "marriage_agency":
        return _marriage_agency_seed_documents()
    if profile.known:
        return _priority_seed_documents(profile)
    return []


def _priority_seed_documents(profile: GenreProfile) -> list[SourceDocument]:
    return [
        _priority_category_doc(profile),
        _priority_target_doc(profile),
        *[_priority_player_doc(profile, player) for player in profile.representative_players[:5]],
    ]


def _priority_category_doc(profile: GenreProfile) -> SourceDocument:
    topic_lines = "\n".join(_topic_line(profile, topic) for topic in profile.category_topics)
    return SourceDocument(
        _category_seed_url(profile),
        f"{profile.canonical_name} カテゴリー基礎",
        f"""
        {profile.canonical_name}は比較検討型の商品・サービスで、サービス/商品の定義を理解してから申し込む。
        利用・購入ステップは情報収集、比較、無料相談、見積もり、申込、契約、利用開始に分かれる。
        料金体系は初期費用、月額費用、成果報酬、手数料、オプション費用、キャンセル条件を確認する。
        比較対象は専門サービス、店舗、オンラインサービス、セルフ対応、他社サービスである。
        主要プレイヤーは大手企業、専門クリニック、専門店、オンライン事業者、比較サイト掲載企業である。
        意思決定基準は価格、実績、口コミ、サポート、保証、利便性、信頼性である。
        リスク・注意点は追加費用、期待外れ、品質差、返金条件、トラブル対応、個人情報の扱いである。
        法規制・広告表現制約は景表法、特商法、業法、医療広告ガイドライン、薬機法などの確認が必要である。
        {topic_lines}
        """,
    )


def _priority_target_doc(profile: GenreProfile) -> SourceDocument:
    segment_text = "、".join(profile.target_segments)
    return SourceDocument(
        _target_seed_url(profile),
        f"{profile.canonical_name} ターゲット基礎",
        f"""
        {profile.canonical_name}のデモグラは{segment_text}に分かれる。
        利用前状態は悩みが顕在化し、複数サービスを比較し、失敗したくない状態である。
        欲求は短期間で解決したい、納得できる価格で利用したい、信頼できる会社を選びたいことである。
        懸念は費用が無駄にならないか、効果が出るか、悪質業者ではないか、手続きが面倒ではないかである。
        ビリーフは専門家や大手なら安心、口コミや実績が多いほど信頼できる、安すぎるサービスは不安という認識である。
        比較対象は専門サービス、店舗、オンラインサービス、セルフ対応、既存の代替手段である。
        購入/申込トリガーは無料相談、キャンペーン、診断、査定、症例、口コミ、ランキングである。
        意思決定基準は価格、実績、口コミ、保証、サポート、スピード、近さ、手軽さである。
        価格の妥当性と追加費用の有無を確認する。
        保証、実績、口コミ、専門性で不安を解消しやすい。
        """,
    )


def _priority_player_doc(profile: GenreProfile, player_name: str) -> SourceDocument:
    return SourceDocument(
        _player_seed_url(profile, player_name),
        f"{player_name} 公式",
        f"""
        {player_name}は{profile.canonical_name}カテゴリの主要プレイヤー。
        特徴はオンライン対応、専門スタッフ、明確な料金、比較しやすいプラン、専門領域に合わせたサポート。
        メリットは検討者の手間を減らし、安心して申し込みや相談に進みやすいこと。
        実績は利用者数、口コミ、事例、症例、満足度、ランキング掲載などで示される。
        権威性は専門家監修、許認可、運営会社の信頼性、医師や歯科医師などの専門職関与で示される。
        オファーは無料相談、無料診断、無料査定、キャンペーン、資料請求、初回相談導線。
        リスク・制約は条件、費用、地域、在庫、適応可否、期待できる結果が利用者ごとに変わること。
        会社情報は運営会社または公式サービスページで確認する。
        """,
    )


def _topic_line(profile: GenreProfile, topic: str) -> str:
    if profile.key == "mouthpiece_orthodontics":
        details = {
            "矯正方式": "矯正方式は透明なマウスピースを段階的に交換して歯を動かす方式と、ワイヤー矯正などの代替手段を比較する。",
            "適応症例": "適応症例は軽度から中等度の歯並び、部分矯正、全体矯正などで、重度症例は歯科医師診断が必要である。",
            "費用": "費用は部分矯正、全体矯正、追加処置、保定装置、通院費用などで総額が変わる。",
            "期間": "期間は症例の難易度、装着時間、治療計画、保定期間によって変わる。",
            "通院頻度": "通院頻度はオンライン管理、定期チェック、歯科医院での診断体制によって異なる。",
            "症例": "症例はBefore After、治療期間、費用、担当歯科医師の説明とセットで確認する。",
            "歯科医師監修": "歯科医師監修は診断、治療計画、適応可否判断、トラブル対応の信頼材料になる。",
            "医療広告制約": "医療広告制約は治療効果の断定、ビフォーアフター表示、体験談、費用表示に注意が必要である。",
        }
        if topic in details:
            return details[topic]
    return f"{topic}は{profile.canonical_name}の比較検討で確認する重要項目である。"


def _category_seed_url(profile: GenreProfile) -> str:
    urls = {
        "gold_purchase": "https://www.npa.go.jp/bureau/safetylife/hoan/kobutsu/index.html",
        "oripa": "https://www.caa.go.jp/policies/policy/representation/fair_labeling/",
        "hair_transplant": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000086878.html",
        "snoring_treatment": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000086878.html",
        "mouthpiece_orthodontics": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000086878.html",
    }
    return urls.get(profile.key, f"https://example.com/{profile.key}/category")


def _target_seed_url(profile: GenreProfile) -> str:
    return f"https://example.com/research-os-seed/{profile.key}/target"


def _player_seed_url(profile: GenreProfile, player_name: str) -> str:
    urls = {
        "なんぼや": "https://nanboya.com/gold-kaitori/",
        "おたからや": "https://www.otakaraya.jp/",
        "大黒屋": "https://kaitori.e-daikoku.com/",
        "DOPA!": "https://dopa-game.jp/",
        "Clove": "https://clove.jp/oripa",
        "日本トレカセンター": "https://japan-toreca.com/",
        "アイランドタワークリニック": "https://www.ilandtower-cl.com/",
        "親和クリニック": "https://shinwa-clinic.jp/",
        "AGAスキンクリニック": "https://www.agaskin.net/",
        "いびきメディカルクリニック": "https://www.ibiki-med.clinic/",
        "スリープメディカルクリニック": "https://sleep-medical.net/",
        "Dクリニック": "https://www.d-clinicgroup.jp/",
        "インビザライン": "https://www.invisalign.co.jp/",
        "キレイライン": "https://kireilign.com/",
        "Oh my teeth": "https://www.oh-my-teeth.com/",
        "ウィ・スマイル": "https://we-smile.jp/",
        "DPEARL": "https://dpearl.jp/",
    }
    return urls.get(player_name, f"https://example.com/research-os-seed/{profile.key}/{player_name}")


def _marriage_agency_seed_documents() -> list[SourceDocument]:
    return [
        SourceDocument(
            "https://www.ibjapan.com/ibj/introduction/",
            "IBJ 日本結婚相談所連盟",
            """
            出会いの方法は自分で検索、カウンセラー紹介、システムによるレコメンド、オフラインイベントに分類される。
            データマッチング、仲人/カウンセラーからの紹介、紹介書による出会い、AIマッチング、会員限定の婚活パーティー開催がある。
            STEP①お見合いでは連絡先交換禁止。STEP②プレ交際では複数交際と新規お見合いが認められる。
            STEP③真剣交際では他の方との交際、新規お見合い、検索システムの利用は停止。
            交際中は性交渉、お泊りNGのルールがある。
            3カ月ルールではお見合いから成婚まで原則3カ月で意思決定する。
            成婚定義は婚約、結婚意思を固めて退会、結婚前提の真剣交際に分かれる。
            成婚までの期間は入会後約5ヶ月から7ヶ月くらいが多い。
            IBJは会員数9万人越え、全国の結婚相談所が連携するネットワーク。
            """,
        ),
        SourceDocument(
            "https://www.nakoudonet.com/",
            "TMS 全国結婚相談事業者連盟",
            """
            TMSは結婚相談所ネットワークで、SCRUM全体で6.7万人規模の会員基盤を持つ。
            TMSは大阪、名古屋、九州など西日本に強い連盟として知られる。
            入会金は銀行振込やクレジットカード、月会費は銀行引き落としやクレジットカードに対応する場合がある。
            大手のカウンセラー数は約80人から200人程度、少人数制の結婚相談所は20人から40人程度。
            比較対象にはマッチングアプリ、婚活パーティー、街コン、知人紹介がある。
            リスクは金銭的損失、時間的損失、強引な成婚誘導への警戒がある。
            """,
        ),
        SourceDocument(
            "https://www.biu.jp/",
            "BIU 日本ブライダル連盟",
            """
            BIUは歴史のある結婚相談所連盟で、地場に根付いた相談所やベテランのカウンセラーが多い。
            コネクトシップは連盟ではなく、会員相互紹介プラットフォームとして利用される。
            コネクトシップでは出会うまでのルールは共通だが、成婚料の有無やサポート内容は入会会社によって異なる。
            """,
        ),
        SourceDocument(
            "https://www.ibjapan.com/ibj/data/",
            "IBJ 成婚白書・会員データ",
            """
            結婚相談所は30代がメインのサービスで、次いで20代・40代と需要が存在する。
            入会者の多くは他の婚活サービスを経験済みで、20代から30代はマッチングアプリ経験後に相談所へ入会する。
            20代男性は20代のうちに結婚したい、結婚前提の出会いを探している。マッチングアプリでは結婚は難しいと感じる。
            20代男性の懸念は経済力のない自分は相手にされないのでは、市場価値が低いのでは、高いお金を払って出会えなかったらどうしよう。
            30代男性はそろそろ本気で結婚を考えたい、早く最短で結婚したい。このまま一人でいいのかと不安。
            30代男性の懸念は魅力的な女性は本当にいるのか、恋愛経験が乏しくても大丈夫か。
            20代女性は30歳までに結婚したい、子どもを複数人授かりたい。マッチングアプリは効率が悪いと感じる。若さが婚活市場の強みになると理解している。
            20代女性の懸念は誰からも選ばれなかったら、純粋な恋愛ができるのか。
            30代女性は最短距離で結婚したい、子どもがほしい。このまま一人で生きていくのかと不安。
            30代女性の懸念は本当に結婚できるのか、遅かったかもしれない、お金も時間も無駄にならないか。
            共通欲求は本気で結婚したいという強い願望。共通懸念は金銭的損失、時間的損失、会員の質、強引な成婚誘導。
            """,
        ),
        _player_doc("https://www.zwei.com/", "ツヴァイ公式", "ツヴァイ", "株式会社ZWEI", "IBJグループ"),
        _player_doc("https://www.sunmarie.co.jp/", "サンマリエ公式", "サンマリエ", "株式会社サンマリエ", "IBJグループ"),
        _player_doc("https://onet.co.jp/", "オーネット公式", "オーネット", "株式会社オーネット", "全国展開"),
        _player_doc("https://www.loungemembers.com/", "IBJメンバーズ公式", "IBJメンバーズ", "株式会社IBJ", "IBJ直営"),
        _player_doc("https://zexy-en-soudan.net/", "ゼクシィ縁結びエージェント公式", "ゼクシィ縁結びエージェント", "株式会社リクルート", "ゼクシィブランド"),
    ]


def _player_doc(url: str, title: str, name: str, company: str, authority: str) -> SourceDocument:
    return SourceDocument(
        url,
        title,
        f"""
        {name}は結婚相談所サービス。
        特徴は紹介書、条件検索、価値観マッチング、店舗またはオンラインのサポート、専任カウンセラー。
        メリットは効率的に結婚前提の相手を探せて、活動中に相談できる安心感があること。
        実績は会員数、成婚退会者、利用者の声、成婚実績を掲載。
        権威性は{authority}として運営される企業信頼。
        オファーは無料相談、資料請求、入会初期費用、月会費、成婚料のプラン。
        リスク・制約は活動費用、地域、希望条件によって紹介数が変わること。
        会社情報は{company}が運営。
        """,
    )
