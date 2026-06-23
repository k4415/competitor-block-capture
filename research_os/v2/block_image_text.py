from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from .block_models import CapturedBlock


RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIBlockImageTextClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 180) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, block: CapturedBlock, *, category_name: str) -> dict[str, str]:
        image_path = Path(block.screenshot_path)
        if not image_path.exists():
            raise RuntimeError(f"screenshot not found: {image_path}")
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": _image_text_prompt(block, category_name)},
                        {"type": "input_image", "image_url": _data_url(image_path), "detail": "high"},
                    ],
                }
            ],
            "text": {"format": {"type": "json_schema", "name": "competitor_block_image_text", "schema": _image_text_schema(), "strict": True}},
        }
        req = urlrequest.Request(
            RESPONSES_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=self.timeout) as response:
            return _extract_json(json.loads(response.read().decode("utf-8")))


def apply_image_text_prompts(
    blocks: list[CapturedBlock],
    *,
    category_name: str,
    client: OpenAIBlockImageTextClient | None = None,
) -> list[CapturedBlock]:
    generator = client or OpenAIBlockImageTextClient()
    if not generator.available():
        raise RuntimeError("OPENAI_API_KEY is required to generate image_text and Template_image_text")

    output: list[CapturedBlock] = []
    for block in blocks:
        if block.status != "取得済み":
            output.append(block)
            continue
        payload = generator.generate(block, category_name=category_name)
        image_text = payload.get("image_text", "")
        template_image_text = payload.get("Template_image_text", "")
        if not image_text or not template_image_text:
            raise RuntimeError(f"OpenAI response did not include image_text and Template_image_text for {block.name}")
        output.append(
            replace(
                block,
                image_text=image_text,
                template_image_text=template_image_text,
                prompt_state="生成済み",
            )
        )
    return output


def _image_text_prompt(block: CapturedBlock, category_name: str) -> str:
    return (
        "競合比較リスティングサイトから切り出した画像素材を解析し、画像生成用の詳細プロンプトを2種類作成してください。"
        "出力はJSON schemaに厳密に従い、値はどちらも文字列にしてください。"
        "`image_text` は、添付画像に近い構図・内容の画像を再生成できるほど詳細な逆算プロンプトです。"
        "`Template_image_text` は、同じ構造を保ちながら、固有名詞、ジャンル名、地域、価格、数値、悩み、訴求、CTAを汎用プレースホルダーに置き換えたテンプレートです。"
        "どちらの文字列も、JSONテキストとして読める形にし、basic、globalDesign、colorScheme、zones、reproductionを必ず含めてください。"
        "Template_image_textでは、必要に応じて {サービス名} {商品名} {ジャンル名} {ターゲット} {価格} {数値} {地域} {悩み} {ベネフィット} {CTA文言} {メインカラー} を使います。"
        "比較リスティング version 3 の画像生成に再利用できるよう、表、ランキング、口コミ、オファー、FAQ、CTA、信頼バッジ、注意書きの構造をテンプレート化してください。"
        "文字入り画像は画像生成モデルにネイティブ生成させる前提で書き、HTML/CSS/Python/Pillow/canvas/スクリーンショット後加工で文字を載せる指示は絶対に含めないでください。"
        "元画像の長いコピーやブランド表現は、image_textでは見た目の再現に必要な範囲で具体化し、Template_image_textでは必ず汎用化してください。"
        "\n\n"
        "参照フォーマット: "
        '{"basic":{"aspectRatio":"1:1","size":"1080x1080px"},"globalDesign":{"style":"","tone":"","targetImpression":"","fontPolicy":{},"spacingPolicy":{},"contrastPolicy":{},"visualStyle":{},"gridAlignment":{},"designRationale":""},"colorScheme":{"main":"","sub":"","accent":"","background":"","usage":{},"designNote":""},"zones":[{"name":"","position":"","purpose":"","background":"","elements":[{"type":"","role":"","description":"","content":"","position":{},"size":"","font":"","color":"","effect":""}]}],"reproduction":{"keyPoints":[],"colorToneNote":"","layoutNote":""}}'
        "\n\n"
        f"カテゴリ: {category_name}\n"
        f"元URL: {block.source_url}\n"
        f"大分類: {block.major_category}\n"
        f"詳細ラベル: {block.detail_label}\n"
        f"セレクタ: {block.selector}\n"
        f"構造メモ: {block.structure_memo}"
    )


def _image_text_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["image_text", "Template_image_text"],
        "properties": {
            "image_text": {"type": "string"},
            "Template_image_text": {"type": "string"},
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
