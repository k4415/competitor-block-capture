from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .config import load_config
from .notion.client import NotionClient
from .notion.pages import (
    build_competitor_properties,
    build_genre_properties,
    build_insight_properties,
    build_lp_plan_properties,
    build_offer_properties,
    build_operation_result_properties,
    build_query_properties,
    build_snapshot_properties,
    build_task_properties,
    build_vendor_brief_properties,
    markdown_to_paragraph_blocks,
)
from .notion.schema import build_database_specs, build_relation_update_properties, without_relation_properties
from .providers.dataforseo import DataForSeoClient, parse_serp_response
from .workflows import analyze_serp_snapshot, export_vendor_pack, generate_vendor_brief


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="listing-os", description="Comparison listing ad workflow OS")
    subcommands = parser.add_subparsers(dest="command", required=True)

    schema = subcommands.add_parser("init-schema", help="Generate or create the Notion database schema")
    schema.add_argument("--parent-page-id", default="")
    schema.add_argument("--config")
    schema.add_argument("--out", default="artifacts/notion-schema.json")
    schema.add_argument("--create", action="store_true", help="Create databases through the Notion API")
    schema.set_defaults(func=cmd_init_schema)

    collect = subcommands.add_parser("collect-serp", help="Collect SERP snapshots from fixture or DataForSEO")
    collect.add_argument("--genre", required=True)
    collect.add_argument("--query", action="append", default=[])
    collect.add_argument("--query-file")
    collect.add_argument("--provider", choices=["fixture", "dataforseo"], default="fixture")
    collect.add_argument("--fixture")
    collect.add_argument("--config")
    collect.add_argument("--device")
    collect.add_argument("--location-code", type=int)
    collect.add_argument("--out", default="artifacts/serp-snapshot.json")
    collect.set_defaults(func=cmd_collect_serp)

    analyze = subcommands.add_parser("analyze-sites", help="Analyze a SERP snapshot and de-duplicate competitor sites")
    analyze.add_argument("--snapshot", required=True)
    analyze.add_argument("--limit", type=int, default=20)
    analyze.add_argument("--out", default="artifacts/site-analysis.json")
    analyze.set_defaults(func=cmd_analyze_sites)

    brief = subcommands.add_parser("generate-brief", help="Generate a comparison LP and vendor handoff brief")
    brief.add_argument("--genre", required=True)
    brief.add_argument("--genre-name", required=True)
    brief.add_argument("--analysis", required=True)
    brief.add_argument("--offers")
    brief.add_argument("--out", default="artifacts/vendor-brief.md")
    brief.set_defaults(func=cmd_generate_brief)

    export = subcommands.add_parser("export-vendor-pack", help="Export a sanitized vendor pack")
    export.add_argument("--brief", required=True)
    export.add_argument("--pack-id", required=True)
    export.add_argument("--out-dir", required=True)
    export.set_defaults(func=cmd_export_vendor_pack)

    sync = subcommands.add_parser("sync-notion", help="Create Notion rows from a SERP analysis and vendor brief")
    sync.add_argument("--database-map", default="artifacts/notion-create-result.json")
    sync.add_argument("--genre", required=True)
    sync.add_argument("--genre-name", required=True)
    sync.add_argument("--query", required=True)
    sync.add_argument("--snapshot", required=True)
    sync.add_argument("--analysis", required=True)
    sync.add_argument("--brief", required=True)
    sync.add_argument("--offers")
    sync.add_argument("--provider", default="fixture")
    sync.add_argument("--device", default="mobile")
    sync.add_argument("--pack-id", required=True)
    sync.add_argument("--out", default="artifacts/notion-sync-result.json")
    sync.set_defaults(func=cmd_sync_notion)

    return parser


def cmd_init_schema(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    parent_page_id = args.parent_page_id or config.notion_parent_page_id
    if not parent_page_id:
        raise SystemExit("--parent-page-id or NOTION_PARENT_PAGE_ID is required")
    specs = build_database_specs(parent_page_id)
    if args.create:
        token = os.getenv("NOTION_API_KEY")
        if not token:
            raise SystemExit("NOTION_API_KEY is required when --create is set")
        notion = NotionClient(token)
        created = []
        data_source_ids = {}
        existing = _discover_existing_databases(notion, parent_page_id, specs)
        for spec in specs:
            if spec["key"] in existing:
                response = {"id": existing[spec["key"]]["database_id"], "data_sources": [{"id": existing[spec["key"]]["data_source_id"]}]}
                reused = True
            else:
                response = notion.create_database(without_relation_properties(spec["request"]))
                reused = False
            data_source_id = _extract_data_source_id(response)
            if not data_source_id and response.get("id"):
                retrieved = notion.retrieve_database(response["id"])
                data_source_id = _extract_data_source_id(retrieved)
            if data_source_id:
                data_source_ids[spec["key"]] = data_source_id
            created.append({"key": spec["key"], "database_id": response.get("id"), "data_source_id": data_source_id, "reused": reused})
        relation_updates = []
        for spec in specs:
            data_source_id = data_source_ids.get(spec["key"])
            if not data_source_id:
                continue
            properties = build_relation_update_properties(spec["request"], data_source_ids=data_source_ids)
            if properties:
                response = notion.update_data_source(data_source_id, {"properties": properties})
                relation_updates.append({"key": spec["key"], "data_source_id": data_source_id, "updated": list(properties), "response_id": response.get("id")})
        _write_json(Path(args.out), {"created": created, "relation_updates": relation_updates})
    else:
        _write_json(Path(args.out), {"databases": specs})
    print(args.out)
    return 0


def cmd_collect_serp(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    queries = _load_queries(args.query, args.query_file)
    if not queries:
        raise SystemExit("At least one --query or --query-file entry is required")
    snapshots = []
    if args.provider == "fixture":
        if not args.fixture:
            raise SystemExit("--fixture is required for fixture provider")
        raw = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        snapshots = raw if isinstance(raw, list) else [raw]
    else:
        if not config.dataforseo_login or not config.dataforseo_password:
            raise SystemExit("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are required")
        client = DataForSeoClient(config.dataforseo_login, config.dataforseo_password)
        for query in queries:
            response = client.collect_serp(
                keyword=query,
                location_code=args.location_code or config.default_location_code,
                language_code=config.default_language_code,
                device=args.device or config.default_device,
                tag=f"{args.genre}:{query}",
            )
            snapshots.append(parse_serp_response(response, genre_id=args.genre, query=query))
    if len(snapshots) == 1:
        payload: Any = snapshots[0]
    else:
        payload = snapshots
    _write_json(Path(args.out), payload)
    print(args.out)
    return 0


def cmd_analyze_sites(args: argparse.Namespace) -> int:
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    if isinstance(snapshot, list):
        analyses = [analyze_serp_snapshot(item, limit=args.limit) for item in snapshot]
        payload: Any = {"analyses": analyses}
    else:
        payload = analyze_serp_snapshot(snapshot, limit=args.limit)
    _write_json(Path(args.out), payload)
    print(args.out)
    return 0


def cmd_generate_brief(args: argparse.Namespace) -> int:
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    offers = json.loads(Path(args.offers).read_text(encoding="utf-8")) if args.offers else []
    markdown = generate_vendor_brief(
        genre_id=args.genre,
        genre_name=args.genre_name,
        analysis=analysis,
        offers=offers,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(args.out)
    return 0


def cmd_export_vendor_pack(args: argparse.Namespace) -> int:
    markdown = Path(args.brief).read_text(encoding="utf-8")
    written = export_vendor_pack(markdown, Path(args.out_dir), args.pack_id)
    print(written["manifest_path"])
    return 0


def cmd_sync_notion(args: argparse.Namespace) -> int:
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is required")
    data_sources = _load_data_source_map(Path(args.database_map))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    offers = json.loads(Path(args.offers).read_text(encoding="utf-8")) if args.offers else []
    brief = Path(args.brief).read_text(encoding="utf-8")
    ranking_axes = _extract_ranking_axes_from_brief(brief)
    notion = NotionClient(token)

    genre_page = notion.create_page(
        data_sources["genres"],
        build_genre_properties(genre_id=args.genre, genre_name=args.genre_name),
    )
    genre_page_id = genre_page["id"]
    query_page = notion.create_page(
        data_sources["queries"],
        build_query_properties(query=args.query, genre_page_id=genre_page_id, device=args.device),
    )
    query_page_id = query_page["id"]
    snapshot_page = notion.create_page(
        data_sources["serp_snapshots"],
        build_snapshot_properties(
            snapshot_name=f"{args.genre_name} {args.query} SERP",
            genre_page_id=genre_page_id,
            query_page_id=query_page_id,
            provider=args.provider,
            device=args.device,
            raw_results=len(snapshot.get("results", [])),
            source_file=str(Path(args.snapshot)),
        ),
    )
    snapshot_page_id = snapshot_page["id"]

    competitor_pages = []
    for site in analysis.get("competitor_sites", []):
        page = notion.create_page(
            data_sources["competitor_sites"],
            build_competitor_properties(site=site, genre_page_id=genre_page_id, snapshot_page_id=snapshot_page_id),
        )
        competitor_pages.append(page["id"])

    offer_pages = []
    for offer in offers:
        page = notion.create_page(data_sources["offers"], build_offer_properties(offer=offer, genre_page_id=genre_page_id))
        offer_pages.append(page["id"])

    insight_pages = []
    for axis in ranking_axes:
        page = notion.create_page(data_sources["insights"], build_insight_properties(genre_page_id=genre_page_id, axis=axis))
        insight_pages.append(page["id"])

    lp_plan_page = notion.create_page(
        data_sources["lp_plans"],
        build_lp_plan_properties(genre_name=args.genre_name, genre_page_id=genre_page_id, ranking_axes=ranking_axes),
        children=markdown_to_paragraph_blocks("比較LP構成案は外注指示パック本文を参照。"),
    )
    vendor_brief_page = notion.create_page(
        data_sources["vendor_briefs"],
        build_vendor_brief_properties(
            genre_name=args.genre_name,
            genre_page_id=genre_page_id,
            lp_plan_page_id=lp_plan_page["id"],
            pack_id=args.pack_id,
            export_path=str(Path(args.brief)),
        ),
        children=markdown_to_paragraph_blocks(brief),
    )
    task_page = notion.create_page(
        data_sources["production_tasks"],
        build_task_properties(genre_name=args.genre_name, genre_page_id=genre_page_id, vendor_brief_page_id=vendor_brief_page["id"]),
    )
    operation_result_page = notion.create_page(
        data_sources["operation_results"],
        build_operation_result_properties(genre_name=args.genre_name, genre_page_id=genre_page_id),
    )

    payload = {
        "genre_page_id": genre_page_id,
        "query_page_id": query_page_id,
        "snapshot_page_id": snapshot_page_id,
        "competitor_page_ids": competitor_pages,
        "offer_page_ids": offer_pages,
        "insight_page_ids": insight_pages,
        "lp_plan_page_id": lp_plan_page["id"],
        "vendor_brief_page_id": vendor_brief_page["id"],
        "task_page_id": task_page["id"],
        "operation_result_page_id": operation_result_page["id"],
    }
    _write_json(Path(args.out), payload)
    print(args.out)
    return 0


def _load_queries(inline_queries: list[str], query_file: str | None) -> list[str]:
    queries = list(inline_queries)
    if query_file:
        queries.extend(
            line.strip()
            for line in Path(query_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return queries


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_data_source_map(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item["key"]: item["data_source_id"] for item in payload.get("created", []) if item.get("data_source_id")}


def _extract_ranking_axes_from_brief(brief: str) -> list[str]:
    axes = []
    in_section = False
    for line in brief.splitlines():
        if line.startswith("## ランキング軸"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("- "):
            axes.append(line.removeprefix("- ").strip())
    return axes or ["料金", "実績", "口コミ", "サポート", "CTA条件"]


def _extract_data_source_id(response: dict[str, Any]) -> str | None:
    data_sources = response.get("data_sources") or []
    if data_sources:
        return data_sources[0].get("id")
    initial = response.get("initial_data_source") or {}
    if initial.get("id"):
        return initial["id"]
    if response.get("object") == "data_source" and response.get("id"):
        return response["id"]
    return None


def _discover_existing_databases(notion: NotionClient, parent_page_id: str, specs: list[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
    wanted_titles = {spec["title"]: spec["key"] for spec in specs}
    found: dict[str, dict[str, str | None]] = {}
    cursor = None
    while True:
        children = notion.list_block_children(parent_page_id, start_cursor=cursor)
        for child in children.get("results", []):
            if child.get("type") != "child_database":
                continue
            title = (child.get("child_database") or {}).get("title")
            key = wanted_titles.get(title)
            if not key or key in found:
                continue
            database_id = child.get("id")
            data_source_id = None
            if database_id:
                retrieved = notion.retrieve_database(database_id)
                data_source_id = _extract_data_source_id(retrieved)
            found[key] = {"database_id": database_id, "data_source_id": data_source_id}
        if not children.get("has_more"):
            break
        cursor = children.get("next_cursor")
        if not cursor:
            break
    return found
