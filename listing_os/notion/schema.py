from __future__ import annotations

from copy import deepcopy
from typing import Any


def _options(names: list[str]) -> list[dict[str, str]]:
    return [{"name": name} for name in names]


DATABASES: list[dict[str, Any]] = [
    {
        "key": "genres",
        "title": "ジャンル",
        "description": "比較リス案件の立ち上げ単位。市場性、優先度、進捗、判断ログを集約する。",
        "properties": {
            "Name": {"title": {}},
            "Status": {"select": {"options": _options(["Backlog", "Researching", "Planning", "Production", "Live", "Paused"])}},
            "Priority": {"select": {"options": _options(["High", "Medium", "Low"])}},
            "Market": {"select": {"options": _options(["Japan"])}},
            "Target": {"rich_text": {}},
            "Decision Log": {"rich_text": {}},
            "Owner": {"people": {}},
        },
    },
    {
        "key": "queries",
        "title": "検索クエリ",
        "description": "SERP/API収集対象のクエリ。ジャンル、意図、地域、デバイスごとに管理する。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Intent": {"select": {"options": _options(["Comparison", "Price", "Review", "Brand", "Problem", "Treatment"])}},
            "Device": {"select": {"options": _options(["mobile", "desktop"])}},
            "Location": {"rich_text": {}},
            "Language": {"rich_text": {}},
            "Enabled": {"checkbox": {}},
        },
    },
    {
        "key": "serp_snapshots",
        "title": "SERPスナップショット",
        "description": "APIから取得した検索結果の実行条件、取得日時、元レスポンスを保存する。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Query": {"relation": {"data_source_id": "__queries__"}},
            "Provider": {"select": {"options": _options(["dataforseo", "serpapi", "fixture"])}},
            "Device": {"select": {"options": _options(["mobile", "desktop"])}},
            "Fetched At": {"date": {}},
            "Raw Results": {"number": {"format": "number"}},
            "Source File": {"url": {}},
        },
    },
    {
        "key": "competitor_sites",
        "title": "競合サイト",
        "description": "SERPから見つかった比較サイト/LPの重複排除済みリストと評価。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Snapshot": {"relation": {"data_source_id": "__serp_snapshots__"}},
            "Domain": {"rich_text": {}},
            "URL": {"url": {}},
            "Best Rank": {"number": {"format": "number"}},
            "Score": {"number": {"format": "number"}},
            "Type": {"select": {"options": _options(["organic", "paid", "mixed"])}},
            "Observed Hooks": {"rich_text": {}},
        },
    },
    {
        "key": "offers",
        "title": "ASP/案件",
        "description": "ASPや一次代理店から入稿される案件情報、報酬、承認条件を保存する。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "ASP": {"rich_text": {}},
            "Commission": {"rich_text": {}},
            "Approval Terms": {"rich_text": {}},
            "Available Claims": {"rich_text": {}},
            "NG Claims": {"rich_text": {}},
            "Status": {"select": {"options": _options(["Candidate", "Requested", "Approved", "Rejected", "Live"])}},
        },
    },
    {
        "key": "insights",
        "title": "訴求インサイト",
        "description": "競合/案件/ターゲット調査から抽出した訴求、判断軸、証拠、注意点。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Source": {"select": {"options": _options(["competitor", "offer", "customer", "operator", "notion_ai"])}},
            "Angle": {"rich_text": {}},
            "Proof": {"rich_text": {}},
            "Risk": {"rich_text": {}},
        },
    },
    {
        "key": "lp_plans",
        "title": "比較LP構成案",
        "description": "比較リス用LPの構成、ランキング軸、原稿骨子、承認状況。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Status": {"select": {"options": _options(["Draft", "Review", "Approved", "Sent", "Live"])}},
            "Ranking Axes": {"rich_text": {}},
            "Hero Copy": {"rich_text": {}},
            "CTA": {"rich_text": {}},
            "Reviewer": {"people": {}},
        },
    },
    {
        "key": "vendor_briefs",
        "title": "外注指示パック",
        "description": "Figma/コーディング外注先に渡す構成、原稿、素材、検収条件。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "LP Plan": {"relation": {"data_source_id": "__lp_plans__"}},
            "Status": {"select": {"options": _options(["Draft", "Ready", "Sent", "In Progress", "Delivered", "Accepted"])}},
            "Pack ID": {"rich_text": {}},
            "Export Path": {"rich_text": {}},
            "Due Date": {"date": {}},
        },
    },
    {
        "key": "production_tasks",
        "title": "制作タスク",
        "description": "デザイン、コーディング、レビュー、修正、公開の実行タスク。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Vendor Brief": {"relation": {"data_source_id": "__vendor_briefs__"}},
            "Status": {"select": {"options": _options(["Todo", "Doing", "Blocked", "Review", "Done"])}},
            "Assignee": {"people": {}},
            "Due Date": {"date": {}},
        },
    },
    {
        "key": "operation_results",
        "title": "運用結果",
        "description": "公開後の数値、学習、次回ジャンル立ち上げへのフィードバック。",
        "properties": {
            "Name": {"title": {}},
            "Genre": {"relation": {"data_source_id": "__genres__"}},
            "Date": {"date": {}},
            "Spend": {"number": {"format": "yen"}},
            "CV": {"number": {"format": "number"}},
            "CPA": {"number": {"format": "yen"}},
            "Learning": {"rich_text": {}},
            "Next Action": {"rich_text": {}},
        },
    },
]


def build_database_specs(parent_page_id: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for db in DATABASES:
        request = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": db["title"]}}],
            "description": [{"type": "text", "text": {"content": db["description"]}}],
            "is_inline": False,
            "initial_data_source": {"properties": deepcopy(db["properties"])},
        }
        specs.append({"key": db["key"], "title": db["title"], "request": request})
    return specs


def relation_order() -> list[str]:
    return [db["key"] for db in DATABASES]


def without_relation_properties(database_request: dict[str, Any]) -> dict[str, Any]:
    request = deepcopy(database_request)
    properties = request["initial_data_source"]["properties"]
    request["initial_data_source"]["properties"] = {
        name: schema for name, schema in properties.items() if "relation" not in schema
    }
    return request


def build_relation_update_properties(
    database_request: dict[str, Any],
    *,
    data_source_ids: dict[str, str],
) -> dict[str, Any]:
    relation_updates: dict[str, Any] = {}
    properties = database_request["initial_data_source"]["properties"]
    for name, schema in properties.items():
        relation = schema.get("relation")
        if not relation:
            continue
        placeholder = relation.get("data_source_id", "")
        target_key = placeholder.removeprefix("__").removesuffix("__")
        target_data_source_id = data_source_ids.get(target_key)
        if target_data_source_id:
            relation_updates[name] = {"relation": {"data_source_id": target_data_source_id, "single_property": {}}}
    return relation_updates
