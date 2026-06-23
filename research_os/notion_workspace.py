from __future__ import annotations

from typing import Any

from .models import ResearchBundle
from .notion_payloads import competitor_page_properties, fact_page_properties, markdown_to_paragraph_blocks, player_page_properties
from .notion_schema import build_research_database_specs


def create_research_workspace(
    *,
    notion: object,
    parent_page_id: str,
    category_name: str,
    memo: str,
    bundle: ResearchBundle,
    research_run_id: str,
) -> dict[str, Any]:
    title = f"{category_name} 比較リスティング調査"
    intro = f"# {title}\n\nResearch Run ID: {research_run_id}\n\n{memo}".strip()
    genre_page = notion.create_child_page(parent_page_id, title, children=markdown_to_paragraph_blocks(intro))
    genre_page_id = genre_page["id"]

    data_sources: dict[str, str] = {}
    databases: dict[str, str] = {}
    for spec in build_research_database_specs(genre_page_id):
        response = notion.create_database(spec.request)
        databases[spec.key] = response.get("id", "")
        data_sources[spec.key] = _extract_data_source_id(response)

    row_ids = {
        "category": _create_fact_rows(notion, data_sources["category"], bundle.category_facts),
        "target": _create_fact_rows(notion, data_sources["target"], bundle.target_facts),
        "players": [
            notion.create_page(
                data_sources["players"],
                player_page_properties(player),
                children=markdown_to_paragraph_blocks(_player_body(player)),
            )["id"]
            for player in bundle.players
        ],
        "competitor_sites": [
            notion.create_page(
                data_sources["competitor_sites"],
                competitor_page_properties(record),
                children=markdown_to_paragraph_blocks(record.full_transcript_summary or record.evidence_snippet),
            )["id"]
            for record in bundle.competitors
        ],
    }
    return {
        "category_page_id": genre_page_id,
        "category_page_url": genre_page.get("url", ""),
        "database_ids": databases,
        "data_source_ids": data_sources,
        "row_ids": row_ids,
        "row_counts": {key: len(value) for key, value in row_ids.items()},
    }


def _create_fact_rows(notion: object, data_source_id: str, facts: list[object]) -> list[str]:
    row_ids = []
    for fact in facts:
        if getattr(fact, "is_usable")():
            row_ids.append(notion.create_page(data_source_id, fact_page_properties(fact))["id"])
    return row_ids


def _player_body(player: object) -> str:
    features = "\n".join(f"- {feature}" for feature in getattr(player, "features", []))
    return (
        f"## 特徴\n{features or '- 未抽出'}\n\n"
        f"## 実績・権威性\n{getattr(player, 'results', '') or '未確認'}\n\n"
        f"## オファー\n{getattr(player, 'offer', '') or '未確認'}\n\n"
        f"## 注意点\n引用元URLで根拠確認後に広告表現へ転用する。"
    )


def _extract_data_source_id(response: dict[str, Any]) -> str:
    data_sources = response.get("data_sources") or []
    if data_sources:
        return data_sources[0].get("id", "")
    initial = response.get("initial_data_source") or {}
    if initial.get("id"):
        return initial["id"]
    if response.get("object") == "data_source":
        return response.get("id", "")
    return ""
