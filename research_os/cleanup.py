from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


LEGACY_DB_KEYS = {
    "genres",
    "queries",
    "serp_snapshots",
    "competitor_sites",
    "offers",
    "insights",
    "lp_plans",
    "vendor_briefs",
    "production_tasks",
    "operation_results",
}


@dataclass(frozen=True)
class LegacyDeleteItem:
    key: str
    database_id: str
    data_source_id: str | None = None


@dataclass(frozen=True)
class LegacyDeletePlan:
    items: list[LegacyDeleteItem]
    skipped_keys: list[str]


def build_legacy_delete_plan(artifact_path: str | Path) -> LegacyDeletePlan:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    items: list[LegacyDeleteItem] = []
    skipped: list[str] = []
    for entry in payload.get("created", []):
        key = entry.get("key", "")
        database_id = entry.get("database_id")
        if key in LEGACY_DB_KEYS and database_id:
            items.append(LegacyDeleteItem(key=key, database_id=database_id, data_source_id=entry.get("data_source_id")))
        elif key:
            skipped.append(key)
    return LegacyDeletePlan(items=items, skipped_keys=skipped)


def trash_legacy_databases(notion_client: object, plan: LegacyDeletePlan) -> list[dict[str, str]]:
    trashed = []
    for item in plan.items:
        notion_client.trash_database(item.database_id)
        trashed.append({"key": item.key, "database_id": item.database_id})
    return trashed
