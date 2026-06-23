from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .block_models import CapturedBlock, DETAIL_LABEL_OPTIONS, MAJOR_CATEGORY_OPTIONS


RICH_TEXT_CHUNK_SIZE = 1900


def required_block_database_properties() -> dict[str, Any]:
    return {
        "名前": {"title": {}},
        "元URL": {"url": {}},
        "ドメイン": {"rich_text": {}},
        "ページタイトル": {"rich_text": {}},
        "Run ID": {"rich_text": {}},
        "表示幅": {"select": {"options": _options(["mobile-390", "desktop-1366"])}},
        "ブロック順": {"number": {}},
        "ブロック大分類": {"select": {"options": _options(MAJOR_CATEGORY_OPTIONS)}},
        "詳細ラベル": {"select": {"options": _options(DETAIL_LABEL_OPTIONS)}},
        "ブロック画像": {"files": {}},
        "構造メモ": {"rich_text": {}},
        "画像生成プロンプト": {"rich_text": {}},
        "image_text": {"rich_text": {}},
        "Template_image_text": {"rich_text": {}},
        "プロンプト状態": {"select": {"options": _options(["生成済み", "未生成", "失敗"])}},
        "信頼度": {"select": {"options": _options(["高", "中", "低"])}},
        "抽出日時": {"date": {}},
        "スクショ範囲": {"rich_text": {}},
        "ステータス": {"select": {"options": _options(["取得済み", "取得失敗", "画像過大"])}},
        "参照レビュー状態": {"select": {"options": _options(["OK", "要確認", "参照なし"])}},
        "参照一致度": {"number": {"format": "number"}},
        "参照レビュー": {"rich_text": {}},
        "参照Run ID": {"rich_text": {}},
    }


def missing_block_database_schema_payload(existing_properties: dict[str, Any]) -> dict[str, Any]:
    required = required_block_database_properties()
    missing = {
        name: spec
        for name, spec in required.items()
        if name not in existing_properties and name != "名前"
    }
    return {"properties": missing}


def sync_captured_blocks_to_notion(*, notion: object, database_id: str, blocks: list[CapturedBlock]) -> dict[str, Any]:
    data_source_id = ensure_block_database_schema(notion=notion, database_id=database_id)
    row_ids: list[str] = []
    uploaded_files: list[dict[str, str]] = []
    for block in blocks:
        file_upload_id = None
        if block.screenshot_path and block.status == "取得済み" and Path(block.screenshot_path).exists():
            file_upload_id = notion.upload_file(block.screenshot_path)
            uploaded_files.append({"block": block.name, "file_upload_id": file_upload_id})
        page = notion.create_page(
            data_source_id,
            block_page_properties(block, file_upload_id=file_upload_id),
            children=block_page_children(block, file_upload_id=file_upload_id),
        )
        row_ids.append(page.get("id", ""))
    return {"data_source_id": data_source_id, "row_ids": row_ids, "uploaded_files": uploaded_files}


def resolve_block_data_source_id(*, notion: object, database_id: str) -> str:
    database = notion.retrieve_database(database_id)
    data_source_id = _extract_data_source_id(database)
    if not data_source_id:
        raise RuntimeError(f"Could not resolve Notion data source ID from database {database_id}")
    return data_source_id


def ensure_block_database_schema(*, notion: object, database_id: str) -> str:
    database = notion.retrieve_database(database_id)
    data_source_id = _extract_data_source_id(database)
    if not data_source_id:
        raise RuntimeError(f"Could not resolve Notion data source ID from database {database_id}")
    existing_properties = _extract_properties(database)
    if not existing_properties and hasattr(notion, "retrieve_data_source"):
        data_source = notion.retrieve_data_source(data_source_id)
        existing_properties = _extract_properties(data_source)
    payload = missing_block_database_schema_payload(existing_properties)
    if payload["properties"]:
        notion.update_data_source(data_source_id, payload)
    return data_source_id


def block_page_properties(block: CapturedBlock, *, file_upload_id: str | None) -> dict[str, Any]:
    return {
        "名前": _title(block.name),
        "元URL": {"url": block.source_url},
        "ドメイン": _rich_text(block.domain),
        "ページタイトル": _rich_text(block.page_title),
        "Run ID": _rich_text(block.run_id),
        "表示幅": _select(block.viewport),
        "ブロック順": {"number": block.order},
        "ブロック大分類": _select(block.major_category),
        "詳細ラベル": _select(block.detail_label),
        "ブロック画像": _files(block, file_upload_id),
        "構造メモ": _rich_text(block.structure_memo),
        "画像生成プロンプト": _rich_text(block.image_prompt),
        "image_text": _rich_text(block.image_text),
        "Template_image_text": _rich_text(block.template_image_text),
        "プロンプト状態": _select(block.prompt_state),
        "信頼度": _select(block.confidence),
        "抽出日時": {"date": {"start": block.extracted_at}},
        "スクショ範囲": _rich_text(json.dumps(block.clip, ensure_ascii=False)),
        "ステータス": _select(block.status),
        "参照レビュー状態": _select(block.reference_review_status),
        "参照一致度": {"number": block.reference_similarity},
        "参照レビュー": _rich_text(block.reference_review_note),
        "参照Run ID": _rich_text(", ".join(block.reference_run_ids)),
    }


def block_page_children(block: CapturedBlock, *, file_upload_id: str | None) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    if file_upload_id:
        children.append(
            {
                "object": "block",
                "type": "image",
                "image": {
                    "caption": [{"type": "text", "text": {"content": block.name}}],
                    "type": "file_upload",
                    "file_upload": {"id": file_upload_id},
                },
            }
        )
    for title, body in [
        ("構造メモ", block.structure_memo),
        ("画像生成プロンプト", block.image_prompt),
        ("参照レビュー", block.reference_review_note),
        ("元URL", block.source_url),
    ]:
        if body:
            children.append(_paragraph(f"{title}: {body}"))
    for title, body in [
        ("image_text", block.image_text),
        ("Template_image_text", block.template_image_text),
    ]:
        if body:
            children.extend(_section_blocks(title, body))
    return children


def _extract_data_source_id(response: dict[str, Any]) -> str:
    for key in ("data_sources", "dataSources"):
        data_sources = response.get(key) or []
        if data_sources:
            return data_sources[0].get("id", "")
    initial = response.get("initial_data_source") or {}
    if initial.get("id"):
        return initial["id"]
    if response.get("object") == "data_source":
        return response.get("id", "")
    return ""


def _extract_properties(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("properties") or (response.get("initial_data_source") or {}).get("properties") or {}


def _title(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": _truncate(text, 2000)}}]}


def _rich_text(text: str) -> dict[str, Any]:
    chunks = _text_chunks(str(text), RICH_TEXT_CHUNK_SIZE)
    return {"rich_text": [{"type": "text", "text": {"content": chunk}} for chunk in chunks]} if chunks else {"rich_text": []}


def _select(name: str) -> dict[str, Any]:
    return {"select": {"name": name or "その他"}}


def _files(block: CapturedBlock, file_upload_id: str | None) -> dict[str, Any]:
    if not file_upload_id:
        return {"files": []}
    filename = Path(block.screenshot_path).name or f"block-{block.order:03d}.png"
    return {
        "files": [
            {
                "type": "file_upload",
                "file_upload": {"id": file_upload_id},
                "name": filename,
            }
        ]
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": _truncate(text, 1800)}}]},
    }


def _section_blocks(title: str, body: str) -> list[dict[str, Any]]:
    blocks = [_heading_3(title)]
    blocks.extend(_paragraph_chunk(chunk) for chunk in _text_chunks(body, RICH_TEXT_CHUNK_SIZE))
    return blocks


def _heading_3(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": _truncate(text, 2000)}}]},
    }


def _paragraph_chunk(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _options(names: list[str]) -> list[dict[str, str]]:
    return [{"name": name} for name in names]


def _truncate(text: str, max_length: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def _text_chunks(text: str, chunk_size: int) -> list[str]:
    cleaned = str(text or "")
    if not cleaned:
        return []
    return [cleaned[index : index + chunk_size] for index in range(0, len(cleaned), chunk_size)]
