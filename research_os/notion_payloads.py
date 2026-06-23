from __future__ import annotations

from typing import Any

from .models import CompetitorSiteRecord, PlayerRecord, ResearchFact


def title_value(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": _truncate(text, 2000)}}]}


def rich_text_value(text: str) -> dict[str, Any]:
    content = _truncate(text, 2000)
    return {"rich_text": [{"type": "text", "text": {"content": content}}]} if content else {"rich_text": []}


def select_value(name: str) -> dict[str, Any]:
    return {"select": {"name": name or "Unknown"}}


def date_value(iso_text: str) -> dict[str, Any]:
    return {"date": {"start": iso_text}}


def fact_page_properties(fact: ResearchFact) -> dict[str, Any]:
    return {
        "Fact": title_value(fact.fact),
        "Category": select_value(fact.category),
        "Source URL": {"url": fact.source_url},
        "Source Title": rich_text_value(fact.source_title),
        "Evidence Snippet": rich_text_value(fact.safe_snippet()),
        "Confidence": select_value(fact.normalized_confidence()),
        "Extracted At": date_value(fact.extracted_at),
        "Research Run ID": rich_text_value(fact.research_run_id),
    }


def player_page_properties(player: PlayerRecord) -> dict[str, Any]:
    return {
        "Fact": title_value(player.player_name),
        "Category": select_value("Service"),
        "Player Name": rich_text_value(player.player_name),
        "Official URL": {"url": player.official_url or player.source_url},
        "Source URL": {"url": player.source_url},
        "Source Title": rich_text_value(player.source_title),
        "Evidence Snippet": rich_text_value(_truncate(player.evidence_snippet, 180)),
        "Confidence": select_value(player.confidence),
        "Extracted At": date_value(player.extracted_at),
        "Research Run ID": rich_text_value(player.research_run_id),
        "Price": rich_text_value(player.price),
        "Plan": rich_text_value(player.plan),
        "Members": rich_text_value(player.members),
        "Results": rich_text_value(player.results),
        "Offer": rich_text_value(player.offer),
    }


def competitor_page_properties(record: CompetitorSiteRecord) -> dict[str, Any]:
    rankings = (record.rankings + ["", "", "", "", ""])[:5]
    return {
        "Fact": title_value(record.domain),
        "Category": select_value("Structure"),
        "Source URL": {"url": record.url},
        "Source Title": rich_text_value(record.source_title),
        "Evidence Snippet": rich_text_value(_truncate(record.evidence_snippet, 180)),
        "Confidence": select_value(record.confidence),
        "Extracted At": date_value(record.extracted_at),
        "Research Run ID": rich_text_value(record.research_run_id),
        "URL": {"url": record.url},
        "Domain": rich_text_value(record.domain),
        "Structure Type": select_value(record.structure_type),
        "Ranking 1": rich_text_value(rankings[0]),
        "Ranking 2": rich_text_value(rankings[1]),
        "Ranking 3": rich_text_value(rankings[2]),
        "Ranking 4": rich_text_value(rankings[3]),
        "Ranking 5": rich_text_value(rankings[4]),
        "Main CTA": rich_text_value(record.main_cta),
        "Listed Players": rich_text_value(" / ".join(record.listed_players)),
        "Direct Competitor": {"checkbox": record.direct_competitor},
    }


def markdown_to_paragraph_blocks(markdown: str, chunk_size: int = 1800) -> list[dict[str, Any]]:
    chunks = [_truncate(markdown[index : index + chunk_size], chunk_size) for index in range(0, len(markdown), chunk_size)] or [""]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        }
        for chunk in chunks
    ]


def _truncate(text: str, max_length: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
