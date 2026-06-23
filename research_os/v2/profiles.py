from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityThreshold:
    category_facts: int
    target_facts: int
    players: int
    competitors: int
    source_count: int = 0


@dataclass(frozen=True)
class GenreProfile:
    key: str
    canonical_name: str
    aliases: tuple[str, ...]
    thresholds: QualityThreshold
    category_type: str = "generic"
    category_topics: tuple[str, ...] = ()
    target_segments: tuple[str, ...] = ("共通",)
    player_discovery_terms: tuple[str, ...] = ()
    source_queries: tuple[str, ...] = ()
    representative_players: tuple[str, ...] = ()
    player_patterns: tuple[str, ...] = ()
    required_category_majors: tuple[str, ...] = ()
    required_target_majors: tuple[str, ...] = ()
    known: bool = True


GENERIC_CATEGORY_TOPICS = (
    "サービス/商品の定義",
    "利用・購入ステップ",
    "料金体系",
    "比較対象",
    "主要プレイヤー",
    "意思決定基準",
    "リスク・注意点",
    "法規制・広告表現制約",
)

GENERIC_TARGET_SEGMENTS = ("20代", "30代", "40代", "50代以上", "男性", "女性", "共通")


MARRIAGE_AGENCY_PROFILE = GenreProfile(
    key="marriage_agency",
    canonical_name="結婚相談所",
    aliases=("結婚相談所", "結婚相談", "婚活相談所", "婚活エージェント"),
    thresholds=QualityThreshold(category_facts=30, target_facts=30, players=5, competitors=1, source_count=4),
    category_type="service",
    category_topics=(
        "出会いの方法",
        "利用ステップ",
        "交際ルール",
        "成婚定義",
        "成婚期間",
        "料金・支払い",
        "カウンセラー体制",
        "連盟・会員基盤",
        "比較対象",
        "リスク・注意点",
    ),
    target_segments=("20代男性", "30代男性", "20代女性", "30代女性", "共通"),
    player_discovery_terms=("公式", "結婚相談所", "無料相談", "資料請求"),
    source_queries=("結婚相談所 仕組み", "結婚相談所 成婚 定義", "結婚相談所 比較"),
    representative_players=("ツヴァイ", "サンマリエ", "オーネット", "IBJメンバーズ", "ゼクシィ縁結びエージェント"),
    player_patterns=("結婚相談所", "婚活エージェント"),
    required_category_majors=("出会いの方法", "利用ステップ", "リスク・注意点"),
    required_target_majors=("デモグラ", "欲求", "懸念"),
)

PRIORITY_PROFILES = (
    GenreProfile(
        key="gold_purchase",
        canonical_name="金買取",
        aliases=("金買取", "金 買取", "貴金属買取", "ブランド買取", "金売却"),
        thresholds=QualityThreshold(category_facts=12, target_facts=10, players=3, competitors=1, source_count=3),
        category_type="purchase",
        category_topics=GENERIC_CATEGORY_TOPICS + ("買取対象", "査定方法", "買取相場", "手数料", "店舗/宅配/出張", "古物営業法", "価格不安"),
        target_segments=GENERIC_TARGET_SEGMENTS + ("高額品売却層", "相場不安層"),
        player_discovery_terms=("金買取", "買取店", "査定", "店舗", "宅配買取", "出張買取"),
        source_queries=("金買取 仕組み", "金買取 手数料", "金買取 古物営業法"),
        representative_players=("なんぼや", "おたからや", "大黒屋"),
        player_patterns=("買取", "査定", "買取店"),
        required_category_majors=("料金体系", "リスク・注意点", "法規制・広告表現制約"),
        required_target_majors=("欲求", "懸念", "意思決定基準"),
    ),
    GenreProfile(
        key="oripa",
        canonical_name="オリパ",
        aliases=("オリパ", "オンラインオリパ", "ポケカオリパ", "トレカオリパ"),
        thresholds=QualityThreshold(category_facts=12, target_facts=10, players=3, competitors=1, source_count=3),
        category_type="commerce",
        category_topics=GENERIC_CATEGORY_TOPICS + ("商品形式", "確率/還元率", "発送", "支払い", "景表法/賭博性リスク", "当たり実績", "信頼性"),
        target_segments=GENERIC_TARGET_SEGMENTS + ("トレカ初心者", "高還元率重視層", "コレクター"),
        player_discovery_terms=("オリパ", "オンラインオリパ", "トレカ", "還元率", "発送", "当たり"),
        source_queries=("オンラインオリパ 仕組み", "オリパ 還元率 確率", "オリパ 景表法"),
        representative_players=("DOPA!", "Clove", "日本トレカセンター"),
        player_patterns=("オリパ", "トレカ", "還元率"),
        required_category_majors=("料金体系", "リスク・注意点", "法規制・広告表現制約"),
        required_target_majors=("欲求", "懸念", "意思決定基準"),
    ),
    GenreProfile(
        key="hair_transplant",
        canonical_name="植毛",
        aliases=("植毛", "自毛植毛", "薄毛治療", "AGA植毛"),
        thresholds=QualityThreshold(category_facts=12, target_facts=10, players=3, competitors=1, source_count=3),
        category_type="medical",
        category_topics=GENERIC_CATEGORY_TOPICS + ("自毛植毛/人工毛", "FUE/FUT", "費用", "症例", "医師/クリニック", "ダウンタイム", "医療広告ガイドライン"),
        target_segments=GENERIC_TARGET_SEGMENTS + ("薄毛悩み層", "AGA経験者", "症例重視層"),
        player_discovery_terms=("植毛", "クリニック", "医師", "症例", "AGA", "無料カウンセリング"),
        source_queries=("自毛植毛 FUE FUT", "植毛 費用 ダウンタイム", "植毛 医療広告ガイドライン"),
        representative_players=("アイランドタワークリニック", "親和クリニック", "AGAスキンクリニック"),
        player_patterns=("植毛", "クリニック", "AGA"),
        required_category_majors=("リスク・注意点", "法規制・広告表現制約"),
        required_target_majors=("欲求", "懸念", "意思決定基準"),
    ),
    GenreProfile(
        key="snoring_treatment",
        canonical_name="いびき治療",
        aliases=("いびき治療", "睡眠時無呼吸", "睡眠時無呼吸症候群", "SAS治療"),
        thresholds=QualityThreshold(category_facts=12, target_facts=10, players=3, competitors=1, source_count=3),
        category_type="medical",
        category_topics=GENERIC_CATEGORY_TOPICS + ("原因", "検査", "CPAP/マウスピース/手術", "保険適用", "睡眠時無呼吸", "医療広告制約"),
        target_segments=GENERIC_TARGET_SEGMENTS + ("睡眠悩み層", "家族指摘層", "CPAP検討層"),
        player_discovery_terms=("いびき", "睡眠時無呼吸", "クリニック", "検査", "CPAP", "マウスピース"),
        source_queries=("いびき治療 原因 検査", "睡眠時無呼吸 CPAP 保険適用", "いびき治療 医療広告"),
        representative_players=("いびきメディカルクリニック", "スリープメディカルクリニック", "Dクリニック"),
        player_patterns=("いびき", "睡眠", "クリニック"),
        required_category_majors=("リスク・注意点", "法規制・広告表現制約"),
        required_target_majors=("欲求", "懸念", "意思決定基準"),
    ),
    GenreProfile(
        key="mouthpiece_orthodontics",
        canonical_name="マウスピース矯正",
        aliases=("マウスピース矯正", "歯列矯正", "インビザライン", "透明矯正"),
        thresholds=QualityThreshold(category_facts=12, target_facts=10, players=3, competitors=1, source_count=3),
        category_type="medical",
        category_topics=GENERIC_CATEGORY_TOPICS + ("矯正方式", "適応症例", "費用", "期間", "通院頻度", "症例", "歯科医師監修", "医療広告制約"),
        target_segments=GENERIC_TARGET_SEGMENTS + ("見た目改善層", "通院負担懸念層", "費用比較層"),
        player_discovery_terms=("マウスピース矯正", "歯科", "症例", "インビザライン", "無料相談", "歯科医師"),
        source_queries=("マウスピース矯正 仕組み", "マウスピース矯正 費用 期間", "マウスピース矯正 医療広告ガイドライン"),
        representative_players=("インビザライン", "キレイライン", "Oh my teeth", "ウィ・スマイル", "DPEARL"),
        player_patterns=("マウスピース矯正", "矯正", "歯科", "インビザライン"),
        required_category_majors=("リスク・注意点", "法規制・広告表現制約"),
        required_target_majors=("欲求", "懸念", "意思決定基準"),
    ),
)

UNKNOWN_PROFILE_THRESHOLD = QualityThreshold(category_facts=20, target_facts=20, players=3, competitors=1, source_count=5)
UNKNOWN_PROFILE = GenreProfile(
    key="unknown",
    canonical_name="",
    aliases=(),
    thresholds=UNKNOWN_PROFILE_THRESHOLD,
    category_type="generic",
    category_topics=GENERIC_CATEGORY_TOPICS,
    target_segments=GENERIC_TARGET_SEGMENTS,
    player_discovery_terms=("公式", "無料相談", "資料請求", "問い合わせ"),
    source_queries=("公式", "比較", "料金"),
    representative_players=(),
    player_patterns=("公式", "サービス", "クリニック", "店舗"),
    required_category_majors=("リスク・注意点",),
    required_target_majors=("欲求", "懸念"),
    known=False,
)


def resolve_genre_profile(category_name: str) -> GenreProfile:
    normalized = _normalize(category_name)
    for profile in (MARRIAGE_AGENCY_PROFILE, *PRIORITY_PROFILES):
        if any(_normalize(alias) in normalized for alias in profile.aliases):
            return profile
    return _unknown_profile(category_name)


def _unknown_profile(category_name: str) -> GenreProfile:
    return GenreProfile(
        key=UNKNOWN_PROFILE.key,
        canonical_name=(category_name or "").strip() or "未指定カテゴリ",
        aliases=UNKNOWN_PROFILE.aliases,
        thresholds=UNKNOWN_PROFILE.thresholds,
        category_type=UNKNOWN_PROFILE.category_type,
        category_topics=UNKNOWN_PROFILE.category_topics,
        target_segments=UNKNOWN_PROFILE.target_segments,
        player_discovery_terms=UNKNOWN_PROFILE.player_discovery_terms,
        source_queries=UNKNOWN_PROFILE.source_queries,
        representative_players=UNKNOWN_PROFILE.representative_players,
        player_patterns=UNKNOWN_PROFILE.player_patterns,
        required_category_majors=UNKNOWN_PROFILE.required_category_majors,
        required_target_majors=UNKNOWN_PROFILE.required_target_majors,
        known=UNKNOWN_PROFILE.known,
    )


def _normalize(value: str) -> str:
    return "".join((value or "").split())


def player_names_for_category(category_name: str = "") -> tuple[str, ...]:
    names: list[str] = []
    profiles = (MARRIAGE_AGENCY_PROFILE, *PRIORITY_PROFILES)
    if category_name:
        profile = resolve_genre_profile(category_name)
        names.extend(profile.representative_players)
    for profile in profiles:
        names.extend(profile.representative_players)
    seen = set()
    output = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            output.append(name)
    return tuple(output)
