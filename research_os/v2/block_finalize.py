from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .block_image_text import OpenAIBlockImageTextClient, apply_image_text_prompts
from .block_models import CapturedBlock
from .block_notion import sync_captured_blocks_to_notion


def finalize_block_capture(
    *,
    run_artifact_path: str | Path,
    category_name: str,
    notion: object,
    database_id: str,
    confirm_reviewed: bool,
    client: OpenAIBlockImageTextClient | None = None,
    out_path: str | Path | None = None,
) -> dict[str, Any]:
    if not confirm_reviewed:
        raise RuntimeError("--confirm-reviewed is required before finalizing block capture results")

    generator = client or OpenAIBlockImageTextClient()
    if not generator.available():
        raise RuntimeError("OPENAI_API_KEY is required to generate image_text and Template_image_text")

    artifact = json.loads(Path(run_artifact_path).read_text(encoding="utf-8"))
    blocks = load_captured_blocks_from_artifact_payload(artifact)
    eligible_blocks = _eligible_blocks_for_finalize(blocks)
    _validate_screenshots(eligible_blocks)

    generated_blocks = apply_image_text_prompts(eligible_blocks, category_name=category_name, client=generator)
    result: dict[str, Any] = {
        "version": "v2-block-capture-finalized",
        "source_run_artifact": str(run_artifact_path),
        "category_name": category_name,
        "notion_database_id": database_id,
        "run": {
            "run_id": (artifact.get("run") or {}).get("run_id", ""),
            "urls": (artifact.get("run") or {}).get("urls", []),
            "viewport": (artifact.get("run") or {}).get("viewport", ""),
            "failed_urls": (artifact.get("run") or {}).get("failed_urls", []),
            "block_count": len(generated_blocks),
            "blocks": [block.to_dict() for block in generated_blocks],
        },
    }
    try:
        result["notion"] = sync_captured_blocks_to_notion(notion=notion, database_id=database_id, blocks=generated_blocks)
    except Exception as error:
        result["notion_error"] = str(error)
        if out_path:
            _write_json(Path(out_path), result)
        raise

    if out_path:
        _write_json(Path(out_path), result)
    return result


def load_captured_blocks_from_artifact_payload(artifact: dict[str, Any]) -> list[CapturedBlock]:
    return [_captured_block_from_dict(item) for item in (artifact.get("run") or {}).get("blocks", [])]


def _eligible_blocks_for_finalize(blocks: list[CapturedBlock]) -> list[CapturedBlock]:
    return [block for block in blocks if block.status == "取得済み"]


def _validate_screenshots(blocks: list[CapturedBlock]) -> None:
    for block in blocks:
        if not block.screenshot_path:
            raise RuntimeError(f"screenshot path is missing for {block.name}")
        if not Path(block.screenshot_path).exists():
            raise RuntimeError(f"screenshot not found for {block.name}: {block.screenshot_path}")


def _captured_block_from_dict(data: dict[str, Any]) -> CapturedBlock:
    return CapturedBlock(
        name=str(data.get("name", "")),
        source_url=str(data.get("source_url", "")),
        domain=str(data.get("domain", "")),
        page_title=str(data.get("page_title", "")),
        run_id=str(data.get("run_id", "")),
        viewport=str(data.get("viewport", "")),
        order=int(data.get("order", 0)),
        major_category=str(data.get("major_category", "その他")),
        detail_label=str(data.get("detail_label", "その他")),
        screenshot_path=str(data.get("screenshot_path", "")),
        structure_memo=str(data.get("structure_memo", "")),
        image_prompt=str(data.get("image_prompt", "")),
        prompt_state=str(data.get("prompt_state", "未生成")),
        confidence=str(data.get("confidence", "低")),
        extracted_at=str(data.get("extracted_at", "")),
        clip=dict(data.get("clip") or {"x": 0, "y": 0, "width": 390, "height": 1}),
        selector=str(data.get("selector", "")),
        status=str(data.get("status", "")),
        image_text=str(data.get("image_text", "")),
        template_image_text=str(data.get("template_image_text") or data.get("Template_image_text") or ""),
        reference_review_status=str(data.get("reference_review_status", "参照なし")),
        reference_similarity=data.get("reference_similarity"),
        reference_review_note=str(data.get("reference_review_note", "")),
        reference_run_ids=tuple(data.get("reference_run_ids") or ()),
        applied_learning_rule_ids=tuple(data.get("applied_learning_rule_ids") or ()),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
