from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def title_value(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text[:2000]}}]}


def rich_text_value(text: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]} if text else {"rich_text": []}


def select_value(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def relation_value(*page_ids: str) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids if page_id]}


def build_genre_properties(*, genre_id: str, genre_name: str) -> dict[str, Any]:
    return {
        "Name": title_value(genre_name),
        "Status": select_value("Researching"),
        "Priority": select_value("High"),
        "Market": select_value("Japan"),
        "Target": rich_text_value("比較リス案件の初期立ち上げ対象"),
        "Decision Log": rich_text_value(f"CLIから作成。genre_id={genre_id}"),
    }


def build_query_properties(*, query: str, genre_page_id: str, device: str = "mobile") -> dict[str, Any]:
    return {
        "Name": title_value(query),
        "Genre": relation_value(genre_page_id),
        "Intent": select_value("Comparison"),
        "Device": select_value(device),
        "Location": rich_text_value("Japan"),
        "Language": rich_text_value("ja"),
        "Enabled": {"checkbox": True},
    }


def build_snapshot_properties(
    *,
    snapshot_name: str,
    genre_page_id: str,
    query_page_id: str,
    provider: str,
    device: str,
    raw_results: int,
    source_file: str,
) -> dict[str, Any]:
    properties = {
        "Name": title_value(snapshot_name),
        "Genre": relation_value(genre_page_id),
        "Query": relation_value(query_page_id),
        "Provider": select_value(provider),
        "Device": select_value(device),
        "Fetched At": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        "Raw Results": {"number": raw_results},
    }
    if source_file.startswith("http"):
        properties["Source File"] = {"url": source_file}
    return properties


def build_competitor_properties(
    *,
    site: dict[str, Any],
    genre_page_id: str,
    snapshot_page_id: str,
) -> dict[str, Any]:
    return {
        "Name": title_value(site.get("domain", "unknown")),
        "Genre": relation_value(genre_page_id),
        "Snapshot": relation_value(snapshot_page_id),
        "Domain": rich_text_value(site.get("domain", "")),
        "URL": {"url": site.get("url") or None},
        "Best Rank": {"number": site.get("best_rank")},
        "Score": {"number": site.get("score")},
        "Type": select_value(site.get("type", "organic")),
        "Observed Hooks": rich_text_value(f"{site.get('title', '')}\n{site.get('description', '')}".strip()),
    }


def build_offer_properties(*, offer: dict[str, Any], genre_page_id: str) -> dict[str, Any]:
    return {
        "Name": title_value(offer.get("name", "未命名案件")),
        "Genre": relation_value(genre_page_id),
        "ASP": rich_text_value(offer.get("asp", "")),
        "Commission": rich_text_value(offer.get("commission", "")),
        "Approval Terms": rich_text_value(offer.get("approval_terms", "")),
        "Available Claims": rich_text_value(offer.get("available_claims", "")),
        "NG Claims": rich_text_value(offer.get("ng_claims", "")),
        "Status": select_value("Candidate"),
    }


def build_lp_plan_properties(*, genre_name: str, genre_page_id: str, ranking_axes: list[str]) -> dict[str, Any]:
    return {
        "Name": title_value(f"{genre_name} 比較LP構成案"),
        "Genre": relation_value(genre_page_id),
        "Status": select_value("Draft"),
        "Ranking Axes": rich_text_value(" / ".join(ranking_axes)),
        "Hero Copy": rich_text_value(f"{genre_name}の選び方とおすすめを比較"),
        "CTA": rich_text_value("無料相談/申込みCTA。案件DBで承認条件を確認してから確定。"),
    }


def build_insight_properties(*, genre_page_id: str, axis: str, source: str = "competitor") -> dict[str, Any]:
    return {
        "Name": title_value(f"{axis} を比較軸として検証"),
        "Genre": relation_value(genre_page_id),
        "Source": select_value(source),
        "Angle": rich_text_value(axis),
        "Proof": rich_text_value("競合SERP/LP観察から抽出。案件DBの証拠で裏取りしてから使用。"),
        "Risk": rich_text_value("未確認のNo.1、効果保証、断定表現に注意。"),
    }


def build_vendor_brief_properties(*, genre_name: str, genre_page_id: str, lp_plan_page_id: str, pack_id: str, export_path: str) -> dict[str, Any]:
    return {
        "Name": title_value(f"{genre_name} 外注指示パック"),
        "Genre": relation_value(genre_page_id),
        "LP Plan": relation_value(lp_plan_page_id),
        "Status": select_value("Ready"),
        "Pack ID": rich_text_value(pack_id),
        "Export Path": rich_text_value(export_path),
    }


def build_task_properties(*, genre_name: str, genre_page_id: str, vendor_brief_page_id: str) -> dict[str, Any]:
    return {
        "Name": title_value(f"{genre_name} 比較LP デザイン/コーディング依頼"),
        "Genre": relation_value(genre_page_id),
        "Vendor Brief": relation_value(vendor_brief_page_id),
        "Status": select_value("Todo"),
    }


def build_operation_result_properties(*, genre_name: str, genre_page_id: str) -> dict[str, Any]:
    return {
        "Name": title_value(f"{genre_name} 初回運用結果入力枠"),
        "Genre": relation_value(genre_page_id),
        "Date": {"date": {"start": datetime.now(timezone.utc).date().isoformat()}},
        "Learning": rich_text_value("運用開始後にCPA/CV/学習を記録する。"),
        "Next Action": rich_text_value("初回配信後に更新。"),
    }


def markdown_to_paragraph_blocks(markdown: str, chunk_size: int = 1800) -> list[dict[str, Any]]:
    chunks = [markdown[index : index + chunk_size] for index in range(0, len(markdown), chunk_size)] or [""]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        }
        for chunk in chunks
    ]
