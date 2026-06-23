from __future__ import annotations

from typing import Any

from .models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Fact


def title_value(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": _truncate(text, 2000)}}]}


def rich_text_value(text: str) -> dict[str, Any]:
    content = _truncate(text, 2000)
    return {"rich_text": [{"type": "text", "text": {"content": content}}]} if content else {"rich_text": []}


def select_value(name: str) -> dict[str, Any]:
    return {"select": {"name": name or "未分類"}}


def date_value(iso_text: str) -> dict[str, Any]:
    return {"date": {"start": iso_text}}


def fact_page_properties(fact: ResearchV2Fact) -> dict[str, Any]:
    return {
        "事実": title_value(fact.fact),
        "大項目": select_value(fact.major_category),
        "小項目": rich_text_value(fact.sub_category),
        "セグメント": select_value(fact.segment),
        "根拠URL": {"url": fact.source_url},
        "根拠タイトル": rich_text_value(fact.source_title),
        "短い引用": rich_text_value(fact.safe_snippet()),
        "信頼度": select_value(fact.normalized_confidence()),
        "検証状態": select_value(fact.normalized_verification_status()),
        "取得日時": date_value(fact.extracted_at),
        "リサーチRun ID": rich_text_value(fact.research_run_id),
    }


def player_page_properties(player: PlayerV2Record) -> dict[str, Any]:
    return {
        "事実": title_value(player.player_name),
        "大項目": select_value("特徴"),
        "小項目": rich_text_value("サービス概要"),
        "セグメント": select_value("サービス"),
        "根拠URL": {"url": player.source_url},
        "根拠タイトル": rich_text_value(player.source_title),
        "短い引用": rich_text_value(_truncate(player.evidence_snippet, 180)),
        "信頼度": select_value(player.normalized_confidence()),
        "検証状態": select_value(player.normalized_verification_status()),
        "取得日時": date_value(player.extracted_at),
        "リサーチRun ID": rich_text_value(player.research_run_id),
        "サービス名": rich_text_value(player.player_name),
        "公式URL": {"url": player.official_url or player.source_url},
        "価格": rich_text_value(player.price),
        "プラン": rich_text_value(player.plan),
        "会員数": rich_text_value(player.members),
        "実績": rich_text_value(player.results),
        "オファー": rich_text_value(player.offer),
    }


def competitor_page_properties(record: CompetitorSiteV2Record) -> dict[str, Any]:
    rankings = (record.rankings + ["", "", "", "", ""])[:5]
    return {
        "事実": title_value(record.domain),
        "大項目": select_value("構成"),
        "小項目": rich_text_value(record.structure_type),
        "セグメント": select_value("直接競合"),
        "根拠URL": {"url": record.url},
        "根拠タイトル": rich_text_value(record.source_title),
        "短い引用": rich_text_value(_truncate(record.evidence_snippet, 180)),
        "信頼度": select_value(record.normalized_confidence()),
        "検証状態": select_value(record.normalized_verification_status()),
        "取得日時": date_value(record.extracted_at),
        "リサーチRun ID": rich_text_value(record.research_run_id),
        "URL": {"url": record.url},
        "ドメイン": rich_text_value(record.domain),
        "構成タイプ": select_value(record.structure_type),
        "ランキング1": rich_text_value(rankings[0]),
        "ランキング2": rich_text_value(rankings[1]),
        "ランキング3": rich_text_value(rankings[2]),
        "ランキング4": rich_text_value(rankings[3]),
        "ランキング5": rich_text_value(rankings[4]),
        "主要CTA": rich_text_value(record.main_cta),
        "掲載サービス": rich_text_value(" / ".join(record.listed_players)),
        "直接競合": {"checkbox": record.direct_competitor},
        "画像内主要文言": rich_text_value(record.image_text_summary),
    }


def markdown_to_paragraph_blocks(markdown: str, chunk_size: int = 1800) -> list[dict[str, Any]]:
    chunks = [markdown[index : index + chunk_size] for index in range(0, len(markdown), chunk_size)] or [""]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": _truncate(chunk, chunk_size)}}]},
        }
        for chunk in chunks
    ]


def player_body(player: PlayerV2Record) -> str:
    lines: list[str] = []
    for section in ["特徴", "メリット", "実績", "権威性", "オファー", "リスク・制約", "会社情報"]:
        values = player.sections.get(section, [])
        lines.append(f"## {section}")
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- 未抽出")
        lines.append("")
    lines.append(f"根拠URL: {player.source_url}")
    return "\n".join(lines).strip()


def _truncate(text: str, max_length: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
