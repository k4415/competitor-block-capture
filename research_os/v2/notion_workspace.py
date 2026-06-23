from __future__ import annotations

from typing import Any

from .models import ResearchV2Bundle
from .notion_payloads import competitor_page_properties, fact_page_properties, markdown_to_paragraph_blocks, player_body, player_page_properties
from .schema import build_v2_research_database_specs


def create_v2_research_workspace(
    *,
    notion: object,
    parent_page_id: str,
    category_name: str,
    memo: str,
    bundle: ResearchV2Bundle,
    research_run_id: str,
    replace_page_ids: list[str] | None = None,
) -> dict[str, Any]:
    trashed_pages = []
    skipped_pages = []
    for page_id in replace_page_ids or []:
        if page_id:
            try:
                trashed_pages.append(notion.trash_page(page_id)["id"])
            except RuntimeError as error:
                if _is_already_archived_error(error):
                    skipped_pages.append(page_id)
                    continue
                raise

    title = f"{category_name} 比較リスティング調査 V2"
    intro = (
        f"# {title}\n\n"
        f"Research Run ID: {research_run_id}\n\n"
        f"収集ソース数: {bundle.source_count}\n\n"
        f"要確認件数: {bundle.needs_review_count()}\n\n"
        f"取得失敗URL: {', '.join(bundle.failed_urls) if bundle.failed_urls else 'なし'}\n\n"
        f"{memo}"
    ).strip()
    genre_page = notion.create_child_page(parent_page_id, title, children=markdown_to_paragraph_blocks(intro))
    genre_page_id = genre_page["id"]

    data_sources: dict[str, str] = {}
    databases: dict[str, str] = {}
    for spec in build_v2_research_database_specs(genre_page_id):
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
                children=markdown_to_paragraph_blocks(player_body(player)),
            )["id"]
            for player in bundle.players
        ],
        "competitor_sites": [
            notion.create_page(
                data_sources["competitor_sites"],
                competitor_page_properties(record),
                children=markdown_to_paragraph_blocks(record.structured_body),
            )["id"]
            for record in bundle.competitors
        ],
    }
    return {
        "version": "v2",
        "category_page_id": genre_page_id,
        "category_page_url": genre_page.get("url", ""),
        "database_ids": databases,
        "data_source_ids": data_sources,
        "row_ids": row_ids,
        "row_counts": {key: len(value) for key, value in row_ids.items()},
        "source_count": bundle.source_count,
        "failed_urls": bundle.failed_urls,
        "needs_review_count": bundle.needs_review_count(),
        "trashed_v1_pages": trashed_pages,
        "skipped_v1_pages": skipped_pages,
    }


def _create_fact_rows(notion: object, data_source_id: str, facts: list[object]) -> list[str]:
    row_ids = []
    for fact in facts:
        if getattr(fact, "is_usable")():
            row_ids.append(notion.create_page(data_source_id, fact_page_properties(fact))["id"])
    return row_ids


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


def _is_already_archived_error(error: RuntimeError) -> bool:
    message = str(error)
    return "Can't edit block that is archived" in message or "unarchive the block before editing" in message
