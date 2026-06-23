from __future__ import annotations

import re

from listing_os.normalization import normalize_domain, normalize_url

from .models import CompetitorSiteRecord, PlayerRecord, ResearchFact, SourceDocument


KNOWN_PLAYER_NAMES = [
    "ツヴァイ",
    "サンマリエ",
    "フィオーレ",
    "IBJメンバーズ",
    "パートナーエージェント",
    "ムスベル",
    "日本仲人協会",
    "オーネット",
    "ゼクシィ縁結びエージェント",
]


class HeuristicExtractor:
    """Deterministic fallback used for tests and no-API local dry-runs."""

    def extract_category_facts(self, docs: list[SourceDocument], *, category_name: str, research_run_id: str) -> list[ResearchFact]:
        facts: list[ResearchFact] = []
        for doc in docs:
            text = _clean(doc.text)
            if "料金" in text or "費用" in text:
                facts.append(_fact("category", f"{category_name}では料金・費用比較が主要な検討材料になる", "Contract", doc, "料金・費用", research_run_id))
            if "無料相談" in text or "無料診断" in text:
                facts.append(_fact("category", f"{category_name}では無料相談や無料診断が初回接点になりやすい", "Step", doc, "無料相談", research_run_id))
            if "成婚" in text:
                facts.append(_fact("category", f"{category_name}では成婚の定義や期間が比較時の重要論点になる", "Rule", doc, "成婚", research_run_id))
        return _dedupe_facts(facts)

    def extract_target_facts(self, docs: list[SourceDocument], *, category_name: str, research_run_id: str) -> list[ResearchFact]:
        facts: list[ResearchFact] = []
        for doc in docs:
            text = _clean(doc.text)
            if "マッチングアプリ" in text:
                facts.append(_fact("target", "比較検討対象としてマッチングアプリが想定される", "Alternative", doc, "マッチングアプリ", research_run_id))
            if "高い" in text or "料金" in text:
                facts.append(_fact("target", "料金が高いのではないかという懸念がある", "Concern", doc, "料金", research_run_id))
            if "本気" in text or "真剣" in text:
                facts.append(_fact("target", "真剣度の高い出会いを求めるユーザーが想定される", "Desire", doc, "真剣", research_run_id))
        return _dedupe_facts(facts)

    def extract_players(self, docs: list[SourceDocument], *, research_run_id: str) -> list[PlayerRecord]:
        records: dict[str, PlayerRecord] = {}
        for doc in docs:
            text = _clean(doc.text)
            for name in KNOWN_PLAYER_NAMES:
                if name in text and name not in records:
                    records[name] = PlayerRecord(
                        player_name=name,
                        source_url=normalize_url(doc.url),
                        source_title=doc.title,
                        evidence_snippet=_snippet_around(text, name),
                        research_run_id=research_run_id,
                        members=_first_match(text, [r"会員数[：:\s]*([0-9\.万万人]+)", r"([0-9\.]+万人)"]),
                        results=_first_match(text, [r"成婚率[：:\s]*([0-9\.％%]+)", r"成婚[^\n。]{0,20}"]),
                        offer=_first_match(text, [r"(無料相談)", r"(無料診断)", r"(無料体験)"]),
                        features=[_snippet_around(text, name)],
                    )
        return list(records.values())

    def extract_competitor_site(self, doc: SourceDocument, *, research_run_id: str, direct: bool) -> CompetitorSiteRecord:
        text = _clean(doc.text)
        rankings = _extract_rankings(text)
        listed_players = [name for name in KNOWN_PLAYER_NAMES if name in text]
        main_cta = _first_match(text, [r"(無料相談)", r"(無料診断)", r"(無料体験)", r"(資料請求)", r"(公式サイトを見る)"])
        structure_type = "Ranking" if rankings else ("Diagnosis" if "診断" in text else "Comparison")
        return CompetitorSiteRecord(
            url=normalize_url(doc.url),
            domain=normalize_domain(doc.url),
            source_title=doc.title,
            structure_type=structure_type,
            rankings=rankings,
            main_cta=main_cta,
            listed_players=listed_players,
            direct_competitor=direct,
            evidence_snippet=_truncate(text, 180),
            research_run_id=research_run_id,
            full_transcript_summary=_truncate(text, 1800),
            confidence="Medium",
        )


def _fact(table: str, fact: str, category: str, doc: SourceDocument, evidence: str, research_run_id: str) -> ResearchFact:
    return ResearchFact(
        table=table,
        fact=fact,
        category=category,
        source_url=normalize_url(doc.url),
        source_title=doc.title,
        evidence_snippet=_snippet_around(_clean(doc.text), evidence),
        confidence="Medium",
        research_run_id=research_run_id,
    )


def _extract_rankings(text: str) -> list[str]:
    rankings: list[str] = []
    for rank in range(1, 6):
        match = re.search(rf"{rank}\s*位\s*([A-Za-z0-9一-龥ぁ-んァ-ヶヴー・&]+)", text)
        rankings.append(match.group(1).strip("。 、,") if match else "")
    if any(rankings):
        return rankings
    found = [name for name in KNOWN_PLAYER_NAMES if name in text]
    return (found + ["", "", "", "", ""])[:5]


def _dedupe_facts(facts: list[ResearchFact]) -> list[ResearchFact]:
    seen = set()
    output = []
    for fact in facts:
        key = (fact.table, fact.fact, fact.source_url)
        if key not in seen and fact.is_usable():
            output.append(fact)
            seen.add(key)
    return output


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
