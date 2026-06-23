from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from .block_finalize import load_captured_blocks_from_artifact_payload
from .block_image_text import OpenAIBlockImageTextClient, apply_image_text_prompts
from .block_models import CapturedBlock
from .block_notion import block_image_text_children, ensure_block_database_schema, block_page_properties


@dataclass(frozen=True)
class ExistingBlockPage:
    page_id: str
    name: str
    source_url: str
    domain: str
    run_id: str
    order: int
    image_text: str
    template_image_text: str
    status: str

    @property
    def needs_backfill(self) -> bool:
        return self.status == "取得済み" and (not self.image_text or not self.template_image_text)


def backfill_block_image_text(
    *,
    notion: object,
    database_id: str,
    category_name: str,
    artifact_paths: list[str | Path],
    confirm_update: bool,
    client: OpenAIBlockImageTextClient | None = None,
    out_path: str | Path | None = None,
    limit: int | None = None,
    concurrency: int = 1,
) -> dict[str, Any]:
    if not confirm_update:
        raise RuntimeError("--confirm-update is required before updating existing Notion pages")

    generator = client or OpenAIBlockImageTextClient()
    if not generator.available():
        raise RuntimeError("OPENAI_API_KEY is required to generate image_text and Template_image_text")

    data_source_id = ensure_block_database_schema(notion=notion, database_id=database_id)
    pages = load_existing_block_pages(notion=notion, data_source_id=data_source_id)
    artifact_index = load_artifact_block_index(artifact_paths)

    targets = [page for page in pages if page.needs_backfill]
    if limit is not None:
        targets = targets[:limit]

    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    matched: list[tuple[ExistingBlockPage, CapturedBlock]] = []
    for page in targets:
        block = _match_artifact_block(page, artifact_index)
        if block is None:
            skipped.append({"page_id": page.page_id, "name": page.name, "reason": "no_matching_local_screenshot"})
            continue
        matched.append((page, block))

    generation_jobs = _generate_blocks(
        matched,
        category_name=category_name,
        client=generator,
        concurrency=concurrency,
    )
    for page, generated, error in generation_jobs:
        if error:
            failed.append({"page_id": page.page_id, "name": page.name, "reason": error})
            continue
        try:
            properties = _backfill_properties(generated)
            notion.update_page(page.page_id, properties)
            children = block_image_text_children(generated)
            if children:
                notion.append_block_children(page.page_id, children)
            updated.append(
                {
                    "page_id": page.page_id,
                    "name": page.name,
                    "run_id": page.run_id,
                    "domain": page.domain,
                    "order": page.order,
                    "screenshot_path": generated.screenshot_path,
                }
            )
        except Exception as error:
            failed.append({"page_id": page.page_id, "name": page.name, "reason": str(error)})

    result: dict[str, Any] = {
        "version": "v2-block-image-text-backfill",
        "category_name": category_name,
        "notion_database_id": database_id,
        "data_source_id": data_source_id,
        "target_count": len(targets),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }
    if out_path:
        _write_json(Path(out_path), result)
    return result


def load_existing_block_pages(*, notion: object, data_source_id: str) -> list[ExistingBlockPage]:
    pages: list[ExistingBlockPage] = []
    next_cursor = None
    while True:
        payload: dict[str, Any] = {"page_size": 100, "sorts": [{"property": "抽出日時", "direction": "ascending"}]}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        response = notion.query_data_source(data_source_id, payload)
        pages.extend(_existing_block_page(page) for page in response.get("results", []))
        if not response.get("has_more"):
            return pages
        next_cursor = response.get("next_cursor")
        if not next_cursor:
            return pages


def load_artifact_block_index(artifact_paths: list[str | Path]) -> dict[tuple[str, str, int], CapturedBlock]:
    index: dict[tuple[str, str, int], CapturedBlock] = {}
    for artifact_path in artifact_paths:
        path = Path(artifact_path)
        if not path.exists():
            continue
        artifact = json.loads(path.read_text(encoding="utf-8"))
        for block in load_captured_blocks_from_artifact_payload(artifact):
            if block.status != "取得済み" or not block.screenshot_path or not Path(block.screenshot_path).exists():
                continue
            index[(block.run_id, block.domain, block.order)] = block
    return index


def _match_artifact_block(page: ExistingBlockPage, index: dict[tuple[str, str, int], CapturedBlock]) -> CapturedBlock | None:
    block = index.get((page.run_id, page.domain, page.order))
    if block is None:
        return None
    return replace(block, name=page.name or block.name)


def _backfill_properties(block: CapturedBlock) -> dict[str, Any]:
    properties = block_page_properties(block, file_upload_id=None)
    return {
        "image_text": properties["image_text"],
        "Template_image_text": properties["Template_image_text"],
        "プロンプト状態": properties["プロンプト状態"],
    }


def _generate_blocks(
    matched: list[tuple[ExistingBlockPage, CapturedBlock]],
    *,
    category_name: str,
    client: OpenAIBlockImageTextClient,
    concurrency: int,
) -> Iterable[tuple[ExistingBlockPage, CapturedBlock, str]]:
    if concurrency <= 1:
        for page, block in matched:
            yield _generate_one(page, block, category_name=category_name, client=client)
        return

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_page = {
            executor.submit(_generate_one, page, block, category_name=category_name, client=client): page
            for page, block in matched
        }
        for future in as_completed(future_to_page):
            yield future.result()


def _generate_one(
    page: ExistingBlockPage,
    block: CapturedBlock,
    *,
    category_name: str,
    client: OpenAIBlockImageTextClient,
) -> tuple[ExistingBlockPage, CapturedBlock, str]:
    try:
        generated = apply_image_text_prompts([block], category_name=category_name, client=client)[0]
        return page, generated, ""
    except Exception as error:
        return page, block, str(error)


def _existing_block_page(page: dict[str, Any]) -> ExistingBlockPage:
    props = page.get("properties") or {}
    return ExistingBlockPage(
        page_id=str(page.get("id", "")),
        name=_text_prop(props.get("名前")),
        source_url=_url_prop(props.get("元URL")),
        domain=_text_prop(props.get("ドメイン")),
        run_id=_text_prop(props.get("Run ID")),
        order=int(_number_prop(props.get("ブロック順")) or 0),
        image_text=_text_prop(props.get("image_text")),
        template_image_text=_text_prop(props.get("Template_image_text")),
        status=_select_prop(props.get("ステータス")) or "取得済み",
    )


def _text_prop(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    rich_text = prop.get("rich_text") or prop.get("title") or []
    return "".join(item.get("plain_text") or (item.get("text") or {}).get("content", "") for item in rich_text)


def _select_prop(prop: dict[str, Any] | None) -> str:
    return ((prop or {}).get("select") or {}).get("name", "")


def _url_prop(prop: dict[str, Any] | None) -> str:
    return (prop or {}).get("url", "")


def _number_prop(prop: dict[str, Any] | None) -> float | int | None:
    return (prop or {}).get("number")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
