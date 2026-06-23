from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchDatabaseSpec:
    key: str
    title: str
    request: dict[str, Any]


def build_research_database_specs(parent_page_id: str) -> list[ResearchDatabaseSpec]:
    return [
        _spec("category", "カテゴリーリサーチ", parent_page_id, _common_properties(_category_options())),
        _spec("target", "ターゲットリサーチ", parent_page_id, _common_properties(_target_options())),
        _spec("players", "メインプレイヤーリサーチ", parent_page_id, _player_properties()),
        _spec("competitor_sites", "競合比較サイトリサーチ", parent_page_id, _competitor_properties()),
    ]


def _spec(key: str, title: str, parent_page_id: str, properties: dict[str, Any]) -> ResearchDatabaseSpec:
    return ResearchDatabaseSpec(
        key=key,
        title=title,
        request={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "is_inline": True,
            "initial_data_source": {"properties": deepcopy(properties)},
        },
    )


def _common_properties(category_options: list[str]) -> dict[str, Any]:
    return {
        "Fact": {"title": {}},
        "Category": {"select": {"options": _options(category_options)}},
        "Source URL": {"url": {}},
        "Source Title": {"rich_text": {}},
        "Evidence Snippet": {"rich_text": {}},
        "Confidence": {"select": {"options": _options(["High", "Medium", "Low"])}},
        "Extracted At": {"date": {}},
        "Research Run ID": {"rich_text": {}},
    }


def _player_properties() -> dict[str, Any]:
    props = _common_properties(["Service", "Price", "Plan", "Members", "Results", "Offer", "Authority", "Feature"])
    props.update(
        {
            "Player Name": {"rich_text": {}},
            "Official URL": {"url": {}},
            "Price": {"rich_text": {}},
            "Plan": {"rich_text": {}},
            "Members": {"rich_text": {}},
            "Results": {"rich_text": {}},
            "Offer": {"rich_text": {}},
        }
    )
    return props


def _competitor_properties() -> dict[str, Any]:
    props = _common_properties(["Structure", "Ranking", "CTA", "Offer", "Proof", "Transcript"])
    props.update(
        {
            "URL": {"url": {}},
            "Domain": {"rich_text": {}},
            "Structure Type": {"select": {"options": _options(["Ranking", "Comparison", "Diagnosis", "Article", "LP", "Unknown"])}},
            "Ranking 1": {"rich_text": {}},
            "Ranking 2": {"rich_text": {}},
            "Ranking 3": {"rich_text": {}},
            "Ranking 4": {"rich_text": {}},
            "Ranking 5": {"rich_text": {}},
            "Main CTA": {"rich_text": {}},
            "Listed Players": {"rich_text": {}},
            "Direct Competitor": {"checkbox": {}},
        }
    )
    return props


def _category_options() -> list[str]:
    return ["Feature", "Contract", "Rule", "Step", "Method", "Alternative", "Market", "Risk"]


def _target_options() -> list[str]:
    return ["Demographic", "Desire", "Alternative", "Concern", "Belief", "Trigger", "Decision Criteria"]


def _options(names: list[str]) -> list[dict[str, str]]:
    return [{"name": name} for name in names]
