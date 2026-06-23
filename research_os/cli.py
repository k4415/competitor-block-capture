from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any

from listing_os.notion.client import NotionClient

from .cleanup import build_legacy_delete_plan, trash_legacy_databases
from .notion_workspace import create_research_workspace
from .runner import ResearchRequest, collect_research_bundle
from .sources import load_source_documents
from .v2.notion_workspace import create_v2_research_workspace
from .v2.block_backfill import backfill_block_image_text
from .v2.block_capture import capture_competitor_blocks, review_captured_blocks
from .v2.block_finalize import finalize_block_capture
from .v2.block_learning import apply_approved_learning_rules, load_approved_learning_rules, write_feedback_learning_payload
from .v2.block_notion import sync_captured_blocks_to_notion
from .v2.block_prompting import analyze_blocks
from .v2.block_reference_review import apply_reference_review_to_blocks, load_reference_blocks_from_notion, no_reference_review, review_blocks_against_references
from .v2.profiles import resolve_genre_profile
from .v2.quality import validate_v2_quality
from .v2.replace import discover_v1_page_ids
from .v2.runner import ResearchV2Request, collect_v2_research_bundle


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os", description="Notion-backed comparison listing research OS")
    subcommands = parser.add_subparsers(dest="command", required=True)

    cleanup = subcommands.add_parser("cleanup-legacy", help="Trash the previous 10-DB listing-os schema")
    cleanup.add_argument("--artifact", default="artifacts/notion-create-result.json")
    cleanup.add_argument("--execute", action="store_true")
    cleanup.add_argument("--out", default="artifacts/research-os-legacy-cleanup.json")
    cleanup.set_defaults(func=cmd_cleanup_legacy)

    run = subcommands.add_parser("run", help="Run a category research workflow and create a Notion workspace")
    run.add_argument("--category-name", required=True)
    run.add_argument("--memo", default="")
    run.add_argument("--depth", default="standard", choices=["light", "standard", "deep"])
    run.add_argument("--parent-page-id", default=os.getenv("NOTION_PARENT_PAGE_ID", "de02e0f0cbe8824ca79201a3b390bd43"))
    run.add_argument("--competitor-url", action="append", default=[])
    run.add_argument("--competitor-url-file")
    run.add_argument("--source-json")
    run.add_argument("--no-openai", action="store_true")
    run.add_argument("--out", default="artifacts/research-os-run-result.json")
    run.set_defaults(func=cmd_run)

    run_v2 = subcommands.add_parser("run-v2", help="Run the V2 high-coverage research workflow and create a Notion workspace")
    run_v2.add_argument("--category-name", required=True)
    run_v2.add_argument("--memo", default="")
    run_v2.add_argument("--depth", default="standard", choices=["light", "standard", "deep"])
    run_v2.add_argument("--parent-page-id", default=os.getenv("NOTION_PARENT_PAGE_ID", "de02e0f0cbe8824ca79201a3b390bd43"))
    run_v2.add_argument("--competitor-url", action="append", default=[])
    run_v2.add_argument("--competitor-url-file")
    run_v2.add_argument("--source-json")
    run_v2.add_argument("--no-openai", action="store_true")
    run_v2.add_argument("--replace-v1", action="store_true")
    run_v2.add_argument("--replace-artifact", action="append", default=[])
    run_v2.add_argument("--replace-page-id", action="append", default=[])
    run_v2.add_argument("--out", default="artifacts/research-os-v2-run-result.json")
    run_v2.set_defaults(func=cmd_run_v2)

    capture_blocks = subcommands.add_parser("capture-blocks", help="Capture semantic visual blocks from competitor comparison listing URLs")
    capture_blocks.add_argument("--category-name", required=True)
    capture_blocks.add_argument("--competitor-url", action="append", default=[])
    capture_blocks.add_argument("--competitor-url-file")
    capture_blocks.add_argument("--notion-database-id", default=os.getenv("COMPETITOR_BLOCK_DB_ID", ""))
    capture_blocks.add_argument("--reference-database-id", default=os.getenv("COMPETITOR_BLOCK_DB_ID", ""))
    capture_blocks.add_argument("--reference-review", dest="reference_review", action="store_true", default=False)
    capture_blocks.add_argument("--no-reference-review", dest="reference_review", action="store_false")
    capture_blocks.add_argument("--fail-on-reference-warning", action="store_true")
    capture_blocks.add_argument("--approved-rules", default="learning/approved_rules.json")
    capture_blocks.add_argument("--max-blocks-per-url", type=int, default=30)
    capture_blocks.add_argument("--no-openai", action="store_true")
    capture_blocks.add_argument("--dry-run", action="store_true")
    capture_blocks.add_argument("--out", default="artifacts/research-os-v2-block-capture-result.json")
    capture_blocks.set_defaults(func=cmd_capture_blocks)

    learn_feedback = subcommands.add_parser("learn-block-feedback", help="Convert block-capture feedback into pending learning rules")
    learn_feedback.add_argument("--run-artifact", required=True)
    learn_feedback.add_argument("--feedback-file", required=True)
    learn_feedback.add_argument("--out", default="learning/pending_rules.json")
    learn_feedback.set_defaults(func=cmd_learn_block_feedback)

    finalize_blocks = subcommands.add_parser("finalize-block-capture", help="Generate approved image prompts and save captured blocks to Notion")
    finalize_blocks.add_argument("--run-artifact", required=True)
    finalize_blocks.add_argument("--category-name", required=True)
    finalize_blocks.add_argument("--notion-database-id", default=os.getenv("COMPETITOR_BLOCK_DB_ID", ""))
    finalize_blocks.add_argument("--confirm-reviewed", action="store_true")
    finalize_blocks.add_argument("--out", default="artifacts/research-os-v2-block-capture-finalized.json")
    finalize_blocks.set_defaults(func=cmd_finalize_block_capture)

    backfill_image_text = subcommands.add_parser("backfill-block-image-text", help="Fill image_text and Template_image_text for existing Notion block rows")
    backfill_image_text.add_argument("--category-name", required=True)
    backfill_image_text.add_argument("--notion-database-id", default=os.getenv("COMPETITOR_BLOCK_DB_ID", ""))
    backfill_image_text.add_argument("--artifact", action="append", default=[])
    backfill_image_text.add_argument("--confirm-update", action="store_true")
    backfill_image_text.add_argument("--limit", type=int)
    backfill_image_text.add_argument("--concurrency", type=int, default=1)
    backfill_image_text.add_argument("--out", default="artifacts/research-os-v2-block-image-text-backfill.json")
    backfill_image_text.set_defaults(func=cmd_backfill_block_image_text)
    return parser


def cmd_cleanup_legacy(args: argparse.Namespace) -> int:
    plan = build_legacy_delete_plan(args.artifact)
    payload: dict[str, Any] = {
        "dry_run": not args.execute,
        "delete_targets": [item.__dict__ for item in plan.items],
        "skipped_keys": plan.skipped_keys,
    }
    if args.execute:
        token = os.getenv("NOTION_API_KEY")
        if not token:
            raise SystemExit("NOTION_API_KEY is required with --execute")
        payload["trashed"] = trash_legacy_databases(NotionClient(token), plan)
    _write_json(Path(args.out), payload)
    print(args.out)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is required")
    competitor_urls = _load_urls(args.competitor_url, args.competitor_url_file)
    docs = load_source_documents(args.source_json) if args.source_json else None
    request = ResearchRequest(
        category_name=args.category_name,
        memo=args.memo,
        depth=args.depth,
        parent_page_id=args.parent_page_id,
        competitor_urls=competitor_urls,
        use_openai=not args.no_openai,
    )
    bundle = collect_research_bundle(request, source_documents=docs)
    result = create_research_workspace(
        notion=NotionClient(token),
        parent_page_id=request.parent_page_id,
        category_name=request.category_name,
        memo=request.memo,
        bundle=bundle,
        research_run_id=request.research_run_id,
    )
    result["research_run_id"] = request.research_run_id
    result["counts"] = bundle.counts()
    _write_json(Path(args.out), result)
    print(args.out)
    return 0


def cmd_run_v2(args: argparse.Namespace) -> int:
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is required")
    competitor_urls = _load_urls(args.competitor_url, args.competitor_url_file)
    docs = load_source_documents(args.source_json) if args.source_json else None
    request = ResearchV2Request(
        category_name=args.category_name,
        memo=args.memo,
        depth=args.depth,
        parent_page_id=args.parent_page_id,
        competitor_urls=competitor_urls,
        use_openai=not args.no_openai,
    )
    replace_page_ids = list(args.replace_page_id)
    if args.replace_v1:
        replace_page_ids.extend(discover_v1_page_ids(args.replace_artifact or None))
    bundle = collect_v2_research_bundle(request, source_documents=docs)
    quality_report = validate_v2_quality(request.category_name, bundle, expected_competitors=len(competitor_urls))
    profile = resolve_genre_profile(request.category_name)
    result = create_v2_research_workspace(
        notion=NotionClient(token),
        parent_page_id=request.parent_page_id,
        category_name=profile.canonical_name,
        memo=request.memo,
        bundle=bundle,
        research_run_id=request.research_run_id,
        replace_page_ids=_dedupe(replace_page_ids),
    )
    result["input_category"] = request.category_name
    result["canonical_category"] = profile.canonical_name
    result["competitor_url_count"] = len(competitor_urls)
    result["notion_created"] = True
    result["quality_status"] = quality_report.status
    result["research_run_id"] = request.research_run_id
    result["counts"] = bundle.counts()
    _write_json(Path(args.out), result)
    print(args.out)
    return 0


def cmd_capture_blocks(args: argparse.Namespace) -> int:
    competitor_urls = _load_urls(args.competitor_url, args.competitor_url_file)
    if not competitor_urls:
        raise SystemExit("At least one --competitor-url or --competitor-url-file entry is required")
    run_id = f"block-run-{uuid.uuid4()}"
    capture_run = capture_competitor_blocks(
        competitor_urls,
        category_name=args.category_name,
        run_id=run_id,
        max_blocks_per_url=args.max_blocks_per_url,
    )
    learning_rules = load_approved_learning_rules(args.approved_rules)
    learning_application = apply_approved_learning_rules(capture_run.blocks, learning_rules)
    learned_blocks = learning_application.blocks
    review_warnings = [*review_captured_blocks(learned_blocks), *learning_application.warnings]

    reference_review = no_reference_review()
    if args.reference_review:
        token = os.getenv("NOTION_API_KEY", "")
        if token and args.reference_database_id:
            references = load_reference_blocks_from_notion(
                notion=NotionClient(token),
                database_id=args.reference_database_id,
                urls=competitor_urls,
                category_name=args.category_name,
                viewport=capture_run.viewport,
            )
            reference_review = review_blocks_against_references(learned_blocks, references, category_name=args.category_name)
        if args.fail_on_reference_warning and reference_review.status == "needs_review":
            raise SystemExit("Reference review found warnings; rerun without --fail-on-reference-warning to save advisory results")
    reviewed_blocks = apply_reference_review_to_blocks(learned_blocks, reference_review)
    analyzed_blocks = analyze_blocks(reviewed_blocks, category_name=args.category_name, use_openai=not args.no_openai)
    result: dict[str, Any] = {
        "version": "v2-block-capture",
        "dry_run": args.dry_run,
        "category_name": args.category_name,
        "notion_database_id": args.notion_database_id,
        "run": {
            "run_id": capture_run.run_id,
            "urls": capture_run.urls,
            "viewport": capture_run.viewport,
            "failed_urls": capture_run.failed_urls,
            "block_count": len(analyzed_blocks),
            "review_warnings": review_warnings,
            "reference_review": reference_review.to_dict(),
            "learning": learning_application.to_dict(),
            "blocks": [block.to_dict() for block in analyzed_blocks],
        },
    }
    if not args.dry_run:
        token = os.getenv("NOTION_API_KEY")
        if not token:
            raise SystemExit("NOTION_API_KEY is required unless --dry-run is set")
        if not args.notion_database_id:
            raise SystemExit("COMPETITOR_BLOCK_DB_ID or --notion-database-id is required unless --dry-run is set")
        result["notion"] = sync_captured_blocks_to_notion(
            notion=NotionClient(token),
            database_id=args.notion_database_id,
            blocks=analyzed_blocks,
        )
    _write_json(Path(args.out), result)
    print(args.out)
    return 0


def cmd_learn_block_feedback(args: argparse.Namespace) -> int:
    write_feedback_learning_payload(run_artifact_path=args.run_artifact, feedback_file=args.feedback_file, out=args.out)
    print(args.out)
    return 0


def cmd_finalize_block_capture(args: argparse.Namespace) -> int:
    if not args.confirm_reviewed:
        raise SystemExit("--confirm-reviewed is required after the user approves the dry-run output")
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is required")
    if not args.notion_database_id:
        raise SystemExit("COMPETITOR_BLOCK_DB_ID or --notion-database-id is required")
    try:
        finalize_block_capture(
            run_artifact_path=args.run_artifact,
            category_name=args.category_name,
            notion=NotionClient(token),
            database_id=args.notion_database_id,
            confirm_reviewed=args.confirm_reviewed,
            out_path=args.out,
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    print(args.out)
    return 0


def cmd_backfill_block_image_text(args: argparse.Namespace) -> int:
    if not args.confirm_update:
        raise SystemExit("--confirm-update is required before updating existing Notion pages")
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is required")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required")
    if not args.notion_database_id:
        raise SystemExit("COMPETITOR_BLOCK_DB_ID or --notion-database-id is required")
    if not args.artifact:
        raise SystemExit("At least one --artifact is required")
    try:
        backfill_block_image_text(
            notion=NotionClient(token),
            database_id=args.notion_database_id,
            category_name=args.category_name,
            artifact_paths=args.artifact,
            confirm_update=args.confirm_update,
            limit=args.limit,
            concurrency=args.concurrency,
            out_path=args.out,
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    print(args.out)
    return 0


def _load_urls(inline_urls: list[str], path: str | None) -> list[str]:
    urls = list(inline_urls)
    if path:
        urls.extend(line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#"))
    return urls


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
