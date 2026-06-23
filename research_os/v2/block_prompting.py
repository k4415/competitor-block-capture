from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from .block_models import CapturedBlock, DETAIL_LABEL_OPTIONS, MAJOR_CATEGORY_OPTIONS


RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIBlockPromptClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 180) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    def analyze(self, block: CapturedBlock, *, category_name: str) -> dict[str, str]:
        image_path = Path(block.screenshot_path)
        if not image_path.exists():
            raise RuntimeError(f"screenshot not found: {image_path}")
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": _analysis_prompt(block, category_name)},
                        {"type": "input_image", "image_url": _data_url(image_path), "detail": "high"},
                    ],
                }
            ],
            "text": {"format": {"type": "json_schema", "name": "competitor_block_prompt", "schema": _analysis_schema(), "strict": True}},
        }
        req = urlrequest.Request(
            RESPONSES_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=self.timeout) as response:
            return _extract_json(json.loads(response.read().decode("utf-8")))


def analyze_blocks(
    blocks: list[CapturedBlock],
    *,
    category_name: str,
    use_openai: bool = True,
    client: OpenAIBlockPromptClient | None = None,
) -> list[CapturedBlock]:
    analyzer = client or OpenAIBlockPromptClient()
    if not use_openai or not analyzer.available():
        reason = "OpenAI analysis skipped: disabled or OPENAI_API_KEY is not configured"
        return [
            replace(block, structure_memo=_append_note(block.structure_memo, reason), prompt_state="未生成")
            for block in blocks
        ]

    analyzed: list[CapturedBlock] = []
    for block in blocks:
        if block.status != "取得済み" or not block.screenshot_path:
            analyzed.append(replace(block, prompt_state="未生成"))
            continue
        try:
            payload = analyzer.analyze(block, category_name=category_name)
            analyzed.append(
                replace(
                    block,
                    major_category=_safe_choice(payload.get("major_category", block.major_category), MAJOR_CATEGORY_OPTIONS, block.major_category),
                    detail_label=_safe_choice(payload.get("detail_label", block.detail_label), DETAIL_LABEL_OPTIONS, block.detail_label),
                    structure_memo=payload.get("structure_memo", block.structure_memo) or block.structure_memo,
                    image_prompt=payload.get("image_prompt", ""),
                    prompt_state="生成済み",
                    confidence=_safe_choice(payload.get("confidence", block.confidence), ["高", "中", "低"], block.confidence),
                )
            )
        except Exception as error:  # noqa: BLE001 - keep Notion sync moving.
            analyzed.append(
                replace(
                    block,
                    structure_memo=_append_note(block.structure_memo, f"OpenAI analysis failed: {error}"),
                    prompt_state="失敗",
                    confidence="低",
                )
            )
    return analyzed


def _analysis_prompt(block: CapturedBlock, category_name: str) -> str:
    return (
        "比較リスティングサイトのスクリーンショットブロックを解析してください。"
        "出力はJSON schemaに厳密に従います。"
        "目的はワイヤーフレーム制作の参考DB化であり、競合サイトのロゴ、ブランド固有表現、長いコピーを完全複製しないでください。"
        "画像生成プロンプトは、元画像に近い構図・情報密度・配色・余白・UI部品・テキスト配置・比較表の列構成・CTA・信頼バッジを再現できる粒度で書きます。"
        "ただし、画像内テキストは画像生成モデルにネイティブ生成させる前提で書き、HTML/CSS/Python/Pillow/canvas/スクリーンショット後加工で文字を載せる指示は絶対に含めないでください。"
        "\n\n"
        f"カテゴリ: {category_name}\n"
        f"元URL: {block.source_url}\n"
        f"既定大分類: {block.major_category}\n"
        f"既定詳細ラベル: {block.detail_label}\n"
        f"セレクタ: {block.selector}\n"
        f"既存メモ: {block.structure_memo}"
    )


def _analysis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["major_category", "detail_label", "structure_memo", "image_prompt", "confidence"],
        "properties": {
            "major_category": {"type": "string", "enum": MAJOR_CATEGORY_OPTIONS},
            "detail_label": {"type": "string", "enum": DETAIL_LABEL_OPTIONS},
            "structure_memo": {"type": "string"},
            "image_prompt": {"type": "string"},
            "confidence": {"type": "string", "enum": ["高", "中", "低"]},
        },
    }


def _data_url(path: Path) -> str:
    content_type = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _extract_json(response: dict[str, Any]) -> dict[str, str]:
    if response.get("output_text"):
        return json.loads(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return json.loads(text)
    raise RuntimeError("OpenAI response did not contain JSON text")


def _append_note(text: str, note: str) -> str:
    if not text:
        return note
    return f"{text}; {note}"


def _safe_choice(value: str, allowed: list[str], fallback: str) -> str:
    return value if value in allowed else fallback
