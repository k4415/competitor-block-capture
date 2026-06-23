from __future__ import annotations

import re
from dataclasses import dataclass

from listing_os.normalization import normalize_domain, normalize_url

from research_os.models import SourceDocument

from .models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Fact
from .profiles import GENERIC_CATEGORY_TOPICS, player_names_for_category, resolve_genre_profile


KNOWN_PLAYER_NAMES = [
    "ツヴァイ",
    "サンマリエ",
    "オーネット",
    "IBJメンバーズ",
    "ゼクシィ縁結びエージェント",
    "パートナーエージェント",
    "フィオーレ",
    "ムスベル",
    "スマリッジ",
    "エン婚活エージェント",
    "naco-do",
]

PLAYER_SECTIONS = ["特徴", "メリット", "実績", "権威性", "オファー", "リスク・制約", "会社情報"]


@dataclass(frozen=True)
class FactTemplate:
    major: str
    sub: str
    segment: str
    fact: str
    evidence: str


class CategoryResearchAgent:
    def extract(self, docs: list[SourceDocument], *, category_name: str, research_run_id: str) -> list[ResearchV2Fact]:
        templates = _category_templates(category_name)
        return _dedupe_facts(_facts_from_templates(templates, docs, research_run_id))


class TargetResearchAgent:
    def extract(self, docs: list[SourceDocument], *, category_name: str, research_run_id: str) -> list[ResearchV2Fact]:
        templates = _target_templates(category_name)
        return _dedupe_facts(_facts_from_templates(templates, docs, research_run_id))


class PlayerResearchAgent:
    def extract(self, docs: list[SourceDocument], *, research_run_id: str, category_name: str = "") -> list[PlayerV2Record]:
        records: dict[str, PlayerV2Record] = {}
        known_names = _known_player_names(category_name)
        for doc in docs:
            text = _clean(doc.text)
            candidate_names = [name for name in known_names if name in text or name in doc.title]
            if not candidate_names and _looks_like_official_player_doc(doc):
                candidate_names = [_guess_player_name(doc, known_names)]
            for name in candidate_names:
                if not name or name in records:
                    continue
                sections = _extract_player_sections(text)
                if not any(sections.values()):
                    continue
                records[name] = PlayerV2Record(
                    player_name=name,
                    official_url=normalize_url(doc.url),
                    source_url=normalize_url(doc.url),
                    source_title=doc.title,
                    evidence_snippet=_snippet_around(text, name if name in text else "特徴"),
                    confidence="高" if "公式" in doc.title or _is_official_like(doc.url) else "中",
                    verification_status="検証済み" if doc.url.startswith("http") else "要確認",
                    research_run_id=research_run_id,
                    sections=sections,
                    price=_first_match(text, [r"(入会[^。]{0,40}円)", r"(月会費[^。]{0,40}円)", r"(成婚料[^。]{0,40}円)"]),
                    plan=_first_match(text, [r"(プラン[^。]{0,80})", r"(コース[^。]{0,80})"]),
                    members=_first_match(text, [r"(会員数[^。]{0,40})", r"([0-9.]+万人[^。]{0,30})"]),
                    results=_first_match(text, [r"(成婚[^。]{0,80})", r"(実績[^。]{0,80})"]),
                    offer=_first_match(text, [r"(無料相談)", r"(無料診断)", r"(資料請求)", r"(来店予約)"]),
                )
        return list(records.values())


class CompetitorSiteResearchAgent:
    def extract(self, docs: list[SourceDocument], *, competitor_urls: list[str], research_run_id: str, category_name: str = "") -> list[CompetitorSiteV2Record]:
        normalized_competitors = {normalize_url(url) for url in competitor_urls if url.strip()}
        if not normalized_competitors:
            return []
        known_names = _known_player_names(category_name)
        records: list[CompetitorSiteV2Record] = []
        for doc in docs:
            normalized_url = normalize_url(doc.url)
            if normalized_url not in normalized_competitors:
                continue
            text = _clean(doc.text)
            rankings = _extract_rankings(text, known_names)
            listed_players = _ordered_known_players(text, known_names)
            main_cta = _first_match(text, [r"(無料相談)", r"(公式サイトを見る)", r"(資料請求)", r"(無料診断)", r"(来店予約)", r"(問い合わせ)"])
            image_text = _extract_labeled_value(text, "画像内テキスト") or _extract_labeled_value(text, "画像内主要文言")
            structured_body = _build_competitor_structured_body(text, rankings, listed_players, main_cta, image_text)
            records.append(
                CompetitorSiteV2Record(
                    url=normalized_url,
                    domain=normalize_domain(doc.url),
                    source_title=doc.title,
                    evidence_snippet=_truncate(text, 180),
                    confidence="高" if rankings else "中",
                    verification_status="検証済み" if doc.url.startswith("http") and "取得失敗" not in text else "取得失敗",
                    research_run_id=research_run_id,
                    structure_type="ランキングLP" if rankings else "比較LP",
                    rankings=rankings,
                    main_cta=main_cta,
                    listed_players=listed_players,
                    image_text_summary=image_text,
                    structured_body=structured_body,
                    direct_competitor=normalized_url in normalized_competitors,
                )
            )
        return records


def _category_templates(category_name: str) -> list[FactTemplate]:
    profile = resolve_genre_profile(category_name)
    if profile.key != "marriage_agency":
        return _generic_category_templates(profile.canonical_name, profile.category_topics)
    return [
        FactTemplate("出会いの方法", "自己検索", "共通", f"{category_name}の出会い方には、自分で検索して申し込む方法がある", "自分で検索"),
        FactTemplate("出会いの方法", "カウンセラー紹介", "共通", f"{category_name}の出会い方には、カウンセラーや仲人から紹介を受ける方法がある", "カウンセラー紹介"),
        FactTemplate("出会いの方法", "レコメンド", "共通", f"{category_name}ではシステムやAIによるレコメンド型の出会い方がある", "レコメンド"),
        FactTemplate("出会いの方法", "イベント", "共通", f"{category_name}ではオフラインイベントや会員限定パーティーも出会い方の一つになる", "オフラインイベント"),
        FactTemplate("利用ステップ", "お見合い", "共通", f"{category_name}の活動初期にはお見合いステップがある", "STEP①"),
        FactTemplate("利用ステップ", "プレ交際", "共通", f"{category_name}ではお見合い後にプレ交際へ進む運用がある", "STEP②"),
        FactTemplate("利用ステップ", "真剣交際", "共通", f"{category_name}ではプレ交際後に真剣交際へ進む運用がある", "STEP③"),
        FactTemplate("交際ルール", "お見合い", "共通", "お見合い段階では連絡先交換が禁止されるルールがある", "連絡先交換禁止"),
        FactTemplate("交際ルール", "プレ交際", "共通", "プレ交際では複数交際と新規お見合いが認められる場合がある", "複数交際"),
        FactTemplate("交際ルール", "真剣交際", "共通", "真剣交際では他の交際や新規お見合い、検索システム利用が停止される場合がある", "検索システムの利用は停止"),
        FactTemplate("交際ルール", "交際禁止事項", "共通", "結婚相談所の交際中には性交渉やお泊まりを禁止するルールがある", "性交渉"),
        FactTemplate("成婚定義", "婚約", "共通", "成婚をプロポーズ成功後の婚約状態と定義する結婚相談所がある", "婚約"),
        FactTemplate("成婚定義", "結婚意思", "共通", "成婚を2人が結婚意思を固めて退会する状態と定義する結婚相談所がある", "結婚意思"),
        FactTemplate("成婚定義", "真剣交際", "共通", "成婚を結婚前提の真剣交際開始と定義する結婚相談所がある", "真剣交際"),
        FactTemplate("成婚期間", "3カ月ルール", "共通", "お見合いから成婚まで原則3カ月で意思決定する3カ月ルールがある", "3カ月ルール"),
        FactTemplate("成婚期間", "平均期間", "共通", "成婚までの期間は入会後5カ月から7カ月程度が一つの目安になる", "5ヶ月"),
        FactTemplate("料金・支払い", "入会金", "共通", "入会金の支払い方法には銀行振込やクレジットカードが含まれる場合がある", "入会金"),
        FactTemplate("料金・支払い", "月会費", "共通", "月会費の支払い方法には銀行引き落としやクレジットカードが含まれる場合がある", "月会費"),
        FactTemplate("カウンセラー体制", "大手", "共通", "大手結婚相談所ではカウンセラー数が80人から200人程度の規模になる場合がある", "80人"),
        FactTemplate("カウンセラー体制", "少人数制", "共通", "少人数制の結婚相談所ではカウンセラー数が20人から40人程度の規模になる場合がある", "20人"),
        FactTemplate("連盟・会員基盤", "IBJ", "共通", "IBJは結婚相談所ネットワークとして会員基盤を提供している", "IBJ"),
        FactTemplate("連盟・会員基盤", "TMS", "共通", "TMSは結婚相談所ネットワークとしてSCRUM等と関連する会員基盤を持つ", "TMS"),
        FactTemplate("連盟・会員基盤", "BIU", "共通", "BIUは歴史のある結婚相談所連盟として言及される", "BIU"),
        FactTemplate("連盟・会員基盤", "コネクトシップ", "共通", "コネクトシップは会員相互紹介プラットフォームとして位置づけられる", "コネクトシップ"),
        FactTemplate("比較対象", "マッチングアプリ", "共通", f"{category_name}の比較対象にはマッチングアプリがある", "マッチングアプリ"),
        FactTemplate("比較対象", "婚活パーティー", "共通", f"{category_name}の比較対象には婚活パーティーがある", "婚活パーティー"),
        FactTemplate("比較対象", "街コン", "共通", f"{category_name}の比較対象には街コンがある", "街コン"),
        FactTemplate("比較対象", "知人紹介", "共通", f"{category_name}の比較対象には知人紹介がある", "知人紹介"),
        FactTemplate("リスク・注意点", "金銭的損失", "共通", f"{category_name}検討者には金銭的損失への不安がある", "金銭的損失"),
        FactTemplate("リスク・注意点", "時間的損失", "共通", f"{category_name}検討者には時間的損失への不安がある", "時間的損失"),
        FactTemplate("リスク・注意点", "成婚誘導", "共通", f"{category_name}検討者には強引な成婚誘導への警戒がある", "強引な成婚誘導"),
    ]


def _target_templates(category_name: str) -> list[FactTemplate]:
    profile = resolve_genre_profile(category_name)
    if profile.key != "marriage_agency":
        return _generic_target_templates(profile.canonical_name)
    return [
        FactTemplate("デモグラ", "年齢", "共通", f"{category_name}は30代がメインで、20代・40代にも需要がある", "30代がメイン"),
        FactTemplate("婚活歴", "経験済み", "共通", f"{category_name}入会者には他の婚活サービス経験済みの層が多い", "経験済み"),
        FactTemplate("比較対象", "マッチングアプリ", "共通", f"{category_name}入会前の比較対象としてマッチングアプリがある", "マッチングアプリ"),
        FactTemplate("欲求", "早期結婚", "20代男性", "20代男性には20代のうちに結婚したい欲求がある", "20代のうちに結婚"),
        FactTemplate("欲求", "結婚前提", "20代男性", "20代男性には結婚前提の出会いを探したい欲求がある", "結婚前提"),
        FactTemplate("状態", "アプリ不信", "20代男性", "20代男性にはマッチングアプリでは結婚が難しいと感じる状態がある", "結婚は難しい"),
        FactTemplate("懸念", "経済力", "20代男性", "20代男性には経済力のない自分は相手にされないのではという懸念がある", "経済力"),
        FactTemplate("懸念", "出会えない不安", "20代男性", "20代男性には高い費用を払っても出会えないのではという懸念がある", "出会えなかったら"),
        FactTemplate("ビリーフ", "市場価値", "20代男性", "20代男性には自分の市場価値が低いのではという認識がある", "市場価値"),
        FactTemplate("欲求", "本気の結婚", "30代男性", "30代男性にはそろそろ本気で結婚を考えたい欲求がある", "本気で結婚"),
        FactTemplate("欲求", "最短結婚", "30代男性", "30代男性には早く最短で結婚したい欲求がある", "最短で結婚"),
        FactTemplate("状態", "将来不安", "30代男性", "30代男性にはこのまま一人でいいのかという不安状態がある", "一人でいいのか"),
        FactTemplate("懸念", "会員の質", "30代男性", "30代男性には魅力的な女性が本当にいるのかという懸念がある", "魅力的な女性"),
        FactTemplate("懸念", "恋愛経験", "30代男性", "30代男性には恋愛経験が乏しくても大丈夫かという懸念がある", "恋愛経験"),
        FactTemplate("意思決定基準", "短期性", "30代男性", "30代男性は最短で結婚できるかを意思決定基準にしやすい", "最短"),
        FactTemplate("欲求", "30歳まで", "20代女性", "20代女性には30歳までに結婚したい欲求がある", "30歳までに結婚"),
        FactTemplate("欲求", "子ども", "20代女性", "20代女性には子どもを複数人授かりたい欲求がある", "子ども"),
        FactTemplate("状態", "アプリ非効率", "20代女性", "20代女性にはマッチングアプリは効率が悪いと感じる状態がある", "効率が悪い"),
        FactTemplate("懸念", "選ばれない不安", "20代女性", "20代女性には誰からも選ばれなかったらという懸念がある", "選ばれなかったら"),
        FactTemplate("懸念", "純粋恋愛", "20代女性", "20代女性には純粋な恋愛ができるのかという懸念がある", "純粋な恋愛"),
        FactTemplate("ビリーフ", "若さ", "20代女性", "20代女性には若さが婚活市場の強みになるという認識がある", "若さ"),
        FactTemplate("欲求", "最短距離", "30代女性", "30代女性には最短距離で結婚したい欲求がある", "最短距離"),
        FactTemplate("欲求", "子ども", "30代女性", "30代女性には子どもがほしいという欲求がある", "子どもがほしい"),
        FactTemplate("状態", "孤独不安", "30代女性", "30代女性にはこのまま一人で生きていくのかという不安状態がある", "一人で生きていく"),
        FactTemplate("懸念", "成婚不安", "30代女性", "30代女性には本当に結婚できるのかという懸念がある", "本当に結婚できる"),
        FactTemplate("懸念", "手遅れ感", "30代女性", "30代女性には遅かったかもしれないという懸念がある", "遅かった"),
        FactTemplate("懸念", "損失不安", "30代女性", "30代女性にはお金も時間も無駄にならないかという懸念がある", "お金も時間も無駄"),
        FactTemplate("欲求", "強い結婚願望", "共通", "共通欲求として本気で結婚したいという強い願望がある", "共通欲求"),
        FactTemplate("懸念", "金銭的損失", "共通", "共通懸念として金銭的損失への不安がある", "金銭的損失"),
        FactTemplate("懸念", "時間的損失", "共通", "共通懸念として時間的損失への不安がある", "時間的損失"),
        FactTemplate("懸念", "会員の質", "共通", "共通懸念として会員の質への疑念がある", "会員の質"),
        FactTemplate("懸念", "成婚誘導", "共通", "共通懸念として強引な成婚誘導への警戒がある", "強引な成婚誘導"),
    ]


def _generic_category_templates(category_name: str, topics: tuple[str, ...]) -> list[FactTemplate]:
    templates: list[FactTemplate] = []
    for topic in topics:
        if topic in GENERIC_CATEGORY_TOPICS:
            templates.append(
                FactTemplate(
                    topic,
                    "概要",
                    "共通",
                    f"{category_name}では「{topic}」を比較検討時に確認する必要がある",
                    topic,
                )
            )
        else:
            templates.append(
                FactTemplate(
                    "カテゴリ固有項目",
                    topic,
                    "共通",
                    f"{category_name}では「{topic}」がカテゴリ固有の重要確認項目になる",
                    topic,
                )
            )
    return templates


def _generic_target_templates(category_name: str) -> list[FactTemplate]:
    return [
        FactTemplate("デモグラ", "年齢・性別", "共通", f"{category_name}検討者は年齢、性別、悩みの強さでセグメントが分かれる", "デモグラ"),
        FactTemplate("利用前状態", "比較検討", "共通", f"{category_name}検討者は複数サービスを比較し、失敗したくない状態にある", "利用前状態"),
        FactTemplate("欲求", "解決", "共通", f"{category_name}検討者には短期間で解決し、納得できる価格で利用したい欲求がある", "欲求"),
        FactTemplate("懸念", "損失・不信", "共通", f"{category_name}検討者には費用対効果、信頼性、手続き負担への懸念がある", "懸念"),
        FactTemplate("ビリーフ", "信頼判断", "共通", f"{category_name}検討者には実績、口コミ、専門性が多いほど信頼しやすい認識がある", "ビリーフ"),
        FactTemplate("比較対象", "代替手段", "共通", f"{category_name}検討者は専門サービス、店舗、オンライン、セルフ対応を比較対象にしやすい", "比較対象"),
        FactTemplate("購入/申込トリガー", "無料導線", "共通", f"{category_name}検討者は無料相談、診断、査定、キャンペーン、ランキングで申込に進みやすい", "購入/申込トリガー"),
        FactTemplate("意思決定基準", "比較軸", "共通", f"{category_name}検討者は価格、実績、口コミ、保証、サポート、スピードを意思決定基準にする", "意思決定基準"),
        FactTemplate("予算感", "価格許容", "共通", f"{category_name}検討者は価格の妥当性と追加費用の有無を確認する", "価格"),
        FactTemplate("不安解消条件", "保証・証拠", "共通", f"{category_name}検討者は保証、実績、口コミ、専門性で不安を解消しやすい", "保証"),
    ]


def _facts_from_templates(templates: list[FactTemplate], docs: list[SourceDocument], research_run_id: str) -> list[ResearchV2Fact]:
    facts: list[ResearchV2Fact] = []
    for template in templates:
        doc = _find_doc_with_evidence(docs, template.evidence)
        if not doc:
            continue
        text = _clean(doc.text)
        facts.append(
            ResearchV2Fact(
                fact=template.fact,
                major_category=template.major,
                sub_category=template.sub,
                segment=template.segment,
                source_url=normalize_url(doc.url),
                source_title=doc.title,
                evidence_snippet=_snippet_around(text, template.evidence),
                confidence="高",
                verification_status="検証済み" if doc.url.startswith("http") else "要確認",
                research_run_id=research_run_id,
            )
        )
    return facts


def _find_doc_with_evidence(docs: list[SourceDocument], evidence: str) -> SourceDocument | None:
    for doc in docs:
        if evidence in doc.text:
            return doc
    return None


def _dedupe_facts(facts: list[ResearchV2Fact]) -> list[ResearchV2Fact]:
    seen = set()
    output = []
    for fact in facts:
        key = (fact.major_category, fact.sub_category, fact.segment, fact.fact, fact.source_url)
        if key not in seen and fact.is_usable():
            seen.add(key)
            output.append(fact)
    return output


def _extract_player_sections(text: str) -> dict[str, list[str]]:
    sections = {name: [] for name in PLAYER_SECTIONS}
    for name in PLAYER_SECTIONS:
        for match in re.finditer(rf"{re.escape(name)}[は：:\s]*([^。]+)", text):
            sections[name].append(_truncate(match.group(1), 180))
    if not sections["特徴"] and ("紹介" in text or "サポート" in text):
        sections["特徴"].append(_snippet_around(text, "特徴"))
    if not sections["メリット"] and ("安心" in text or "効率" in text):
        sections["メリット"].append(_snippet_around(text, "メリット"))
    if not sections["実績"] and ("会員" in text or "成婚" in text or "症例" in text or "実績" in text):
        sections["実績"].append(_snippet_around(text, "実績"))
    if not sections["権威性"] and ("IBJ" in text or "グループ" in text or "専門家" in text or "医師" in text or "歯科医師" in text or "許認可" in text):
        sections["権威性"].append(_snippet_around(text, "権威性"))
    if not sections["オファー"] and ("無料相談" in text or "資料請求" in text or "無料診断" in text or "無料査定" in text):
        sections["オファー"].append(_snippet_around(text, "無料相談"))
    if not sections["リスク・制約"] and ("費用" in text or "地域" in text or "条件" in text or "適応" in text):
        sections["リスク・制約"].append(_snippet_around(text, "費用"))
    if not sections["会社情報"] and ("株式会社" in text or "運営" in text):
        sections["会社情報"].append(_snippet_around(text, "株式会社"))
    return sections


def _looks_like_official_player_doc(doc: SourceDocument) -> bool:
    return _is_official_like(doc.url) or "公式" in doc.title


def _guess_player_name(doc: SourceDocument, known_names: tuple[str, ...]) -> str:
    for name in known_names:
        if name in doc.title or name in doc.url:
            return name
    return doc.title.replace("公式", "").strip()[:40]


def _is_official_like(url: str) -> bool:
    return any(
        domain in url
        for domain in [
            "zwei.com",
            "sunmarie.co.jp",
            "onet.co.jp",
            "ibjapan.com",
            "zexy-en-soudan.net",
            "invisalign.co.jp",
            "kireilign.com",
            "oh-my-teeth.com",
            "we-smile.jp",
            "dpearl.jp",
            "nanboya.com",
            "otakaraya.jp",
            "e-daikoku.com",
            "ilandtower-cl.com",
            "shinwa-clinic.jp",
            "agaskin.net",
        ]
    )


def _extract_rankings(text: str, known_names: tuple[str, ...]) -> list[str]:
    rankings: list[str] = []
    for rank in range(1, 6):
        line_match = re.search(rf"{rank}\s*位\s*([^。。\n]+)", text)
        line = line_match.group(1) if line_match else ""
        name = next((player for player in known_names if player in line), "")
        rankings.append(name)
    if any(rankings):
        return rankings
    found = _ordered_known_players(text, known_names)
    return (found + ["", "", "", "", ""])[:5]


def _ordered_known_players(text: str, known_names: tuple[str, ...]) -> list[str]:
    positions = [(text.find(name), name) for name in known_names if name in text]
    return [name for _, name in sorted(positions)]


def _known_player_names(category_name: str = "") -> tuple[str, ...]:
    names = list(player_names_for_category(category_name))
    for name in KNOWN_PLAYER_NAMES:
        if name not in names:
            names.append(name)
    return tuple(names)


def _extract_labeled_value(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}[：:\s]*([^。]+)", text)
    return match.group(1).strip() if match else ""


def _build_competitor_structured_body(text: str, rankings: list[str], listed_players: list[str], main_cta: str, image_text: str) -> str:
    headings = _extract_labeled_value(text, "見出し")
    comparison_axes = _extract_labeled_value(text, "比較軸")
    proof = _extract_labeled_value(text, "証拠表現")
    appeal = _extract_labeled_value(text, "訴求パターン")
    lines = [
        "## 構成順",
        f"- ファーストビュー/主要見出し: {headings or '未抽出'}",
        f"- ランキング提示: {' / '.join([item for item in rankings if item]) or '未抽出'}",
        f"- CTA配置: {main_cta or '未抽出'}",
        "",
        "## 見出し",
        f"- {headings or '未抽出'}",
        "",
        "## ランキング1-5",
    ]
    for index, name in enumerate((rankings + ["", "", "", "", ""])[:5], start=1):
        lines.append(f"- {index}位: {name or '未抽出'}")
    lines.extend(
        [
            "",
            "## CTA",
            f"- {main_cta or '未抽出'}",
            "",
            "## 掲載サービス",
            f"- {' / '.join(listed_players) or '未抽出'}",
            "",
            "## 画像内主要文言",
            f"- {image_text or '未抽出'}",
            "",
            "## 比較軸",
            f"- {comparison_axes or '未抽出'}",
            "",
            "## 証拠表現",
            f"- {proof or '未抽出'}",
            "",
            "## 訴求パターン",
            f"- {appeal or '未抽出'}",
            "",
            "## 短い根拠引用",
            f"- {_truncate(text, 180)}",
        ]
    )
    return _truncate("\n".join(lines), 2400)


def _snippet_around(text: str, needle: str, max_length: int = 180) -> str:
    if not needle or needle not in text:
        return _truncate(text, max_length)
    index = text.find(needle)
    start = max(0, index - 60)
    end = min(len(text), index + len(needle) + 80)
    return _truncate(text[start:end], max_length)


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return (match.group(1) if match.groups() else match.group(0)).strip()
    return ""


def _clean(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, max_length: int) -> str:
    cleaned = _clean(text)
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
