from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import floor
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .block_models import BlockCaptureRun, CapturedBlock


VIEWPORT_NAME = "mobile-390"
VIEWPORT = {"width": 390, "height": 1200}
MAX_NOTION_DIRECT_UPLOAD_BYTES = 20 * 1024 * 1024
PNG_TO_JPEG_THRESHOLD_BYTES = 18 * 1024 * 1024
MAX_VIEWPORT_SCREENSHOT_HEIGHT = 3600
OVERSIZED_PARENT_HEIGHT = 2400
CANDIDATE_SELECTOR_PARTS = [
    "header",
    "main > section",
    "main > article",
    "article > section",
    "section",
    "article",
    "table",
    '[role="table"]',
    '[class*="hero"]',
    '[class*="fv"]',
    '[class*="first"]',
    '[class*="compare"]',
    '[class*="comparison"]',
    '[class*="hikaku"]',
    '[class*="rank"]',
    '[id*="rank"]',
    'section[id*="ranking"] > div > div > ul > li',
    'section[id*="ranking"] > div > div > ul > li div.wrap',
    'section[id*="ranking"] > div > div > ul > li dl.case',
    'section[id*="ranking"] > div > div > ul > li div.check',
    'section[id*="ranking"] > div > div > ul > li dl.point',
    'section[id*="ranking"] > div > div > ul > li [class*="location"]',
    "#rank_box > ul > li > table",
    "#rank_box > ul > li > div.recommendation",
    "#rank_box > ul > li > section.case-section",
    "#rank_box > ul > li > div.reviews",
    "#rank_box > ul > li > div.campaign",
    "#rank_box > ul > li > div.store-locations",
    "#rank_box > ul > li > p.btn",
    "div.hikaku_table",
    "main#main_content > div > div > figure",
    "main#main_content > div > div > div.wp-block-sbd-checkpoint-block",
    "main#main_content > div > div > p.has-border",
    '[class*="faq"]',
    '[id*="faq"]',
    '[class*="qa"]',
    '[class*="cta"]',
    '[id*="cta"]',
]


@dataclass(frozen=True)
class RawBlockCandidate:
    selector: str
    tag: str
    text: str
    x: float
    y: float
    width: float
    height: float
    class_name: str = ""
    element_id: str = ""

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class Classification:
    major_category: str
    detail_label: str
    confidence: str


@dataclass(frozen=True)
class ScreenshotPlan:
    scroll_y: int
    clip: dict[str, int]


def capture_competitor_blocks(
    urls: Iterable[str],
    *,
    category_name: str,
    run_id: str | None = None,
    artifact_dir: str | Path = "artifacts/research-os-v2/block-captures",
    max_blocks_per_url: int = 30,
) -> BlockCaptureRun:
    url_list = [url for url in urls if url]
    run_id = run_id or f"block-run-{uuid.uuid4()}"
    artifact_root = Path(artifact_dir) / run_id
    blocks: list[CapturedBlock] = []
    failed_urls: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:  # noqa: BLE001 - optional dependency.
        raise RuntimeError('Playwright is required. Install with: python3 -m pip install -e ".[browser]"') from error

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, user_agent="Mozilla/5.0 research-os block capture")
        for index, url in enumerate(url_list, start=1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:  # noqa: BLE001 - many ad LPs keep network connections open.
                    pass
                _lazy_scroll(page)
                page_title = page.title() or url
                candidates = _extract_candidates(page)
                screenshot_dir = artifact_root / f"{index:02d}-{_safe_slug(_domain_from_url(url))}"
                selected = select_semantic_blocks(
                    url=url,
                    page_title=page_title,
                    category_name=category_name,
                    run_id=run_id,
                    candidates=candidates,
                    screenshot_dir=screenshot_dir,
                    max_blocks=max_blocks_per_url,
                )
                blocks.extend(_write_block_screenshots(page, selected))
            except Exception as error:  # noqa: BLE001 - keep batch jobs moving.
                failed_urls.append(url)
                blocks.append(_failed_block(url, category_name, run_id, index, str(error)))
        browser.close()

    return BlockCaptureRun(run_id=run_id, category_name=category_name, urls=url_list, viewport=VIEWPORT_NAME, blocks=blocks, failed_urls=failed_urls)


def select_semantic_blocks(
    *,
    url: str,
    page_title: str,
    category_name: str,
    run_id: str,
    candidates: list[RawBlockCandidate],
    screenshot_dir: Path,
    max_blocks: int,
) -> list[CapturedBlock]:
    domain = _domain_from_url(url)
    filtered = [_normalize_candidate(candidate) for candidate in candidates if _candidate_is_usable(candidate)]
    filtered.sort(key=lambda candidate: (candidate.y, 1 if "::first-view" in candidate.selector else 0, -candidate.height, candidate.selector))
    filtered = _cap_synthetic_first_view(filtered)
    filtered = _drop_nested_first_view_children(filtered)
    filtered = _tighten_per_item_card_bounds(filtered)
    filtered = _drop_children_of_per_item_cards(filtered)
    filtered = _merge_wordpress_article_runs(filtered)
    filtered = _merge_visual_comparison_groups(filtered)
    filtered = _drop_large_visual_overlaps(filtered)
    filtered = _merge_adjacent_ranking_ctas(filtered)
    filtered = _drop_oversized_parents_with_children(filtered)

    selected: list[RawBlockCandidate] = []
    for candidate in filtered:
        if "::first-view" in candidate.selector and any(existing.y < 80 and existing.height >= 220 for existing in selected):
            continue
        if any(_is_nested_duplicate(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_blocks:
            break

    blocks: list[CapturedBlock] = []
    extracted_at = datetime.now(timezone.utc).isoformat()
    for order, candidate in enumerate(selected, start=1):
        classification = classify_candidate(candidate, order=order)
        screenshot_path = screenshot_dir / f"{order:03d}-{_safe_slug(classification.detail_label)}.png"
        text_summary = _truncate(candidate.text, 260)
        blocks.append(
            CapturedBlock(
                name=f"{category_name} {domain} {order:03d} {classification.detail_label}",
                source_url=url,
                domain=domain,
                page_title=page_title,
                run_id=run_id,
                viewport=VIEWPORT_NAME,
                order=order,
                major_category=classification.major_category,
                detail_label=classification.detail_label,
                screenshot_path=str(screenshot_path),
                structure_memo=f"selector={candidate.selector}; tag={candidate.tag}; text={text_summary}",
                image_prompt="",
                prompt_state="未生成",
                confidence=classification.confidence,
                extracted_at=extracted_at,
                clip={"x": candidate.x, "y": candidate.y, "width": candidate.width, "height": candidate.height},
                selector=candidate.selector,
                status="取得済み",
            )
        )
    return blocks


def classify_candidate(candidate: RawBlockCandidate, *, order: int) -> Classification:
    haystack = " ".join([candidate.tag, candidate.class_name, candidate.element_id, candidate.text]).lower()
    japanese = candidate.text
    if _is_ranking_basic_info_candidate(candidate):
        return Classification("個別候補詳細", "個別候補の基本情報", "高")
    if _is_ranking_case_candidate(candidate):
        return Classification("個別候補詳細", "効果/症例/Before After", "高")
    if _is_ranking_supported_type_candidate(candidate):
        return Classification("解決方法・選択肢理解", "向いている人/向かない人", "高")
    if _is_ranking_point_candidate(candidate):
        return Classification("ランキング", "おすすめポイント要約", "高")
    if _is_ranking_location_candidate(candidate):
        return Classification("個別候補詳細", "店舗/地域一覧", "高")
    if _is_review_candidate(candidate):
        return Classification("個別候補詳細", "口コミ/体験談", "高")
    if _is_limited_offer_candidate(candidate):
        return Classification("クロージング", "限定オファー", "高")
    if _is_rank_cta_candidate(candidate):
        return Classification("クロージング", "CTA反復", "高")
    if _is_per_item_comparison_card(candidate):
        return Classification("ランキング", "ランキング本文", "高")
    if _is_product_feature_card(candidate):
        return Classification("個別候補詳細", "個別候補の基本情報", "高")
    if _is_single_product_detail_table(candidate):
        return Classification("個別候補詳細", "個別候補の詳細比較", "高")
    if _is_selection_criteria_candidate(candidate):
        return Classification("選び方・評価基準", "選び方3〜5ポイント", "高")
    if _is_wordpress_product_detail_candidate(candidate):
        return Classification("個別候補詳細", "個別候補の基本情報", "高")
    if _is_wordpress_explainer_image_candidate(candidate):
        return Classification("選び方・評価基準", "選び方3〜5ポイント", "中")
    if candidate.y < 700:
        if _contains_any(haystack, ["hero", "fv", "first", "mainvisual"]) or _contains_any(japanese, ["最新版", "おすすめ", "ランキング", "top", "無料相談"]):
            return Classification("ファーストビュー", "ファーストビュー結論", "高")
    if _is_ranking_candidate(candidate):
        return Classification("ランキング", "ランキング本文", "高")
    if (
        candidate.tag in {"table", "thead", "tbody"}
        or _contains_any(haystack, ["compare", "comparison", "hikaku", "table", "top3"])
        or _contains_any(japanese, ["比較表", "料金", "会員数", "横スクロール"])
        or _looks_like_comparison_matrix(japanese)
    ):
        return Classification("比較表", "一括比較表", "高")
    if _contains_any(haystack, ["ranking", "rank", "best", "card"]) or _contains_any(japanese, ["ランキング", "1位", "2位", "3位", "best", "top3", "top5"]):
        return Classification("ランキング", "ランキング本文", "高")
    if _contains_any(haystack, ["faq", "qa", "question"]) or _contains_any(japanese, ["よくある質問", "faq", "q&a", "質問"]):
        return Classification("行動前不安解消", "FAQ/Q&A", "高")
    if _contains_any(haystack, ["cta", "conversion", "offer"]) or _contains_any(japanese, ["公式サイト", "無料相談", "予約", "今すぐ", "詳細を見る"]):
        return Classification("クロージング", "CTA反復", "中")
    if _contains_any(japanese, ["選び方", "チェックリスト", "評価基準", "調査方法"]):
        return Classification("選び方・評価基準", "選び方3〜5ポイント", "中")
    if _contains_any(japanese, ["費用", "料金", "価格", "総額", "分割"]):
        return Classification("費用・負担理解", "価格体系の基礎解説", "中")
    if _contains_any(japanese, ["悩み", "不安", "リスク", "失敗", "後悔"]):
        return Classification("ランキング前説明", "悩み共感リスト", "中")
    if _contains_any(japanese, ["流れ", "手順", "ステップ"]):
        return Classification("行動前不安解消", "利用・施術の流れ", "中")
    return Classification("その他", "その他", "低")


def _extract_candidates(page: Any) -> list[RawBlockCandidate]:
    raw_candidates = page.evaluate(
        """
        () => {
          const cssPath = (el) => {
            if (!el || el === document.body) return 'body';
            const parts = [];
            while (el && el.nodeType === Node.ELEMENT_NODE && el !== document.body) {
              let part = el.tagName.toLowerCase();
              if (el.id) {
                part += '#' + CSS.escape(el.id);
                parts.unshift(part);
                break;
              }
              const parent = el.parentElement;
              if (parent) {
                const siblings = Array.from(parent.children).filter((sib) => sib.tagName === el.tagName);
                if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(el) + 1})`;
              }
              parts.unshift(part);
              el = parent;
            }
            return ['body', ...parts].join(' > ');
          };
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const candidates = [];
          const pageWidth = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 390);
          candidates.push({
            selector: 'body::first-view',
            tag: 'section',
            text: clean(document.body.innerText).slice(0, 1600),
            x: 0,
            y: 0,
            width: pageWidth,
            height: Math.min(900, Math.max(420, window.innerHeight || 900)),
            class_name: 'first-view',
            element_id: ''
          });
          const selector = __CANDIDATE_SELECTOR_PARTS__.join(',');
          for (const el of document.querySelectorAll(selector)) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const text = clean(el.innerText || el.textContent);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const actionContext = [el.className, el.id, text].join(' ');
            const minHeight = /btn|公式サイト|空き枠|詳細を見る|予約/i.test(actionContext) ? 50 : 80;
            if (rect.width < 220 || rect.height < minHeight) continue;
            if (text.length < 12 && !['TABLE', 'HEADER'].includes(el.tagName)) continue;
            candidates.push({
              selector: cssPath(el),
              tag: el.tagName.toLowerCase(),
              text,
              x: Math.max(0, rect.left + window.scrollX),
              y: Math.max(0, rect.top + window.scrollY),
              width: Math.max(1, rect.width),
              height: Math.max(1, rect.height),
              class_name: clean(el.className && typeof el.className === 'string' ? el.className : ''),
              element_id: el.id || ''
            });
          }
          return candidates;
        }
        """.replace("__CANDIDATE_SELECTOR_PARTS__", json.dumps(CANDIDATE_SELECTOR_PARTS, ensure_ascii=False))
    )
    return [
        RawBlockCandidate(
            selector=str(item.get("selector", "")),
            tag=str(item.get("tag", "")),
            text=str(item.get("text", "")),
            x=float(item.get("x", 0)),
            y=float(item.get("y", 0)),
            width=float(item.get("width", 0)),
            height=float(item.get("height", 0)),
            class_name=str(item.get("class_name", "")),
            element_id=str(item.get("element_id", "")),
        )
        for item in raw_candidates
    ]


def _write_block_screenshots(page: Any, blocks: list[CapturedBlock]) -> list[CapturedBlock]:
    output: list[CapturedBlock] = []
    page_height = float(page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, window.innerHeight)"))
    for block in blocks:
        path = Path(block.screenshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        clip = safe_screenshot_clip(block.clip, page_height=page_height, page_width=float(VIEWPORT["width"]))
        viewport_height = max(VIEWPORT["height"], min(MAX_VIEWPORT_SCREENSHOT_HEIGHT, int(clip["height"]) + 20))
        screenshot_plan = viewport_relative_screenshot_plan(clip, viewport_height=viewport_height)
        try:
            page.set_viewport_size({"width": VIEWPORT["width"], "height": viewport_height})
            page.evaluate("(y) => window.scrollTo(0, y)", screenshot_plan.scroll_y)
            page.wait_for_timeout(120)
            page.screenshot(path=str(path), clip=screenshot_plan.clip, timeout=15000)
            if path.stat().st_size > PNG_TO_JPEG_THRESHOLD_BYTES:
                jpeg_path = path.with_suffix(".jpg")
                page.screenshot(path=str(jpeg_path), type="jpeg", quality=82, clip=screenshot_plan.clip, timeout=15000)
                path.unlink(missing_ok=True)
                path = jpeg_path
            output.append(_finalize_screenshot_block(block, path, clip))
        except Exception as error:  # noqa: BLE001 - one bad clip should not discard the page.
            if block.selector and "::" not in block.selector:
                try:
                    page.locator(block.selector).first.screenshot(path=str(path), timeout=5000)
                    output.append(_finalize_screenshot_block(block, path, clip))
                    continue
                except Exception as fallback_error:  # noqa: BLE001 - preserve the original clip error too.
                    error = RuntimeError(f"{error}; locator fallback failed: {fallback_error}")
            output.append(
                replace(
                    block,
                    screenshot_path="",
                    status="取得失敗",
                    structure_memo=f"{block.structure_memo}; screenshot failed: {error}",
                    clip=clip,
                )
            )
    return output


def _finalize_screenshot_block(block: CapturedBlock, path: Path, clip: dict[str, int]) -> CapturedBlock:
    if path.stat().st_size > MAX_NOTION_DIRECT_UPLOAD_BYTES:
        return replace(block, screenshot_path=str(path), status="画像過大", structure_memo=f"{block.structure_memo}; image exceeds 20MB", clip=clip)
    return replace(block, screenshot_path=str(path), clip=clip)


def safe_screenshot_clip(clip: dict[str, float], *, page_height: float, page_width: float) -> dict[str, int]:
    x = floor(max(0, float(clip["x"])))
    y = floor(max(0, min(float(clip["y"]), page_height - 1)))
    width = floor(max(1, min(float(clip["width"]), page_width - x - 1)))
    bottom_margin = 9
    height = floor(max(1, min(float(clip["height"]), max(1, page_height - y - bottom_margin))))
    return {"x": x, "y": y, "width": width, "height": height}


def viewport_relative_screenshot_plan(clip: dict[str, int], *, viewport_height: int) -> ScreenshotPlan:
    scroll_y = int(max(0, clip["y"]))
    relative_y = int(max(0, clip["y"] - scroll_y))
    height = int(min(clip["height"], max(1, viewport_height - relative_y)))
    return ScreenshotPlan(
        scroll_y=scroll_y,
        clip={"x": int(clip["x"]), "y": relative_y, "width": int(clip["width"]), "height": height},
    )


def _failed_block(url: str, category_name: str, run_id: str, order: int, reason: str) -> CapturedBlock:
    extracted_at = datetime.now(timezone.utc).isoformat()
    domain = _domain_from_url(url)
    return CapturedBlock(
        name=f"{category_name} {domain} {order:03d} 取得失敗",
        source_url=url,
        domain=domain,
        page_title=url,
        run_id=run_id,
        viewport=VIEWPORT_NAME,
        order=order,
        major_category="その他",
        detail_label="その他",
        screenshot_path="",
        structure_memo=f"取得失敗: {reason}",
        image_prompt="",
        prompt_state="未生成",
        confidence="低",
        extracted_at=extracted_at,
        clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": 0},
        selector="",
        status="取得失敗",
    )


def _lazy_scroll(page: Any) -> None:
    page.evaluate(
        """
        async () => {
          const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const maxY = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          for (let y = 0; y < maxY; y += 900) {
            window.scrollTo(0, y);
            await delay(120);
          }
          window.scrollTo(0, 0);
          await delay(120);
        }
        """
    )


def _candidate_is_usable(candidate: RawBlockCandidate) -> bool:
    min_height = 50 if _is_small_action_candidate(candidate) else 80
    if candidate.width < 220 or candidate.height < min_height:
        return False
    if len(candidate.text.strip()) < 12 and candidate.tag not in {"table", "header"}:
        return False
    return True


def _is_small_action_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    return _contains_any(haystack, ["btn", "公式サイト", "空き枠", "詳細を見る", "予約"])


def _normalize_candidate(candidate: RawBlockCandidate) -> RawBlockCandidate:
    return RawBlockCandidate(
        selector=candidate.selector,
        tag=candidate.tag.lower(),
        text=" ".join(candidate.text.split()),
        x=max(0, candidate.x),
        y=max(0, candidate.y),
        width=max(1, min(candidate.width, VIEWPORT["width"])),
        height=max(1, candidate.height),
        class_name=candidate.class_name,
        element_id=candidate.element_id,
    )


def _cap_synthetic_first_view(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    capped: list[RawBlockCandidate] = []
    for candidate in candidates:
        if candidate.selector != "body::first-view":
            capped.append(candidate)
            continue
        boundary = _first_full_width_section_y_after_first_view(candidates, candidate)
        if boundary is None:
            capped.append(candidate)
            continue
        capped.append(replace(candidate, height=max(1, boundary - candidate.y)))
    return capped


def _first_full_width_section_y_after_first_view(candidates: list[RawBlockCandidate], first_view: RawBlockCandidate) -> float | None:
    boundaries = [candidate.y for candidate in candidates if _is_first_view_boundary_candidate(candidate, first_view)]
    if not boundaries:
        return None
    return min(boundaries)


def _is_first_view_boundary_candidate(candidate: RawBlockCandidate, first_view: RawBlockCandidate) -> bool:
    if candidate.selector == first_view.selector:
        return False
    if candidate.y <= first_view.y + 260 or candidate.y >= first_view.bottom:
        return False
    if candidate.width < VIEWPORT["width"] * 0.75 or candidate.height < 160:
        return False
    if _is_wordpress_explainer_image_candidate(candidate):
        return True
    context = " ".join([candidate.selector, candidate.class_name, candidate.element_id, candidate.text])
    return _contains_any(context, ["ランキング", "top3", "比較", "voice", "rank", "選び方", "料金", "おすすめ"])


def _drop_nested_first_view_children(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    first_views = [candidate for candidate in candidates if candidate.selector == "body::first-view"]
    if not first_views:
        return candidates
    first_view = first_views[0]
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if candidate.selector == first_view.selector:
            output.append(candidate)
            continue
        if candidate.y > first_view.y + 20 and candidate.y < first_view.bottom and candidate.bottom <= first_view.bottom + 1:
            continue
        output.append(candidate)
    return output


def _drop_children_of_per_item_cards(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    per_item_cards = [candidate for candidate in candidates if _is_per_item_comparison_card(candidate)]
    if not per_item_cards:
        return candidates
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if any(_is_meaningful_child(candidate, card) for card in per_item_cards):
            continue
        output.append(candidate)
    return output


def _tighten_per_item_card_bounds(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if not _is_per_item_comparison_card(candidate):
            output.append(candidate)
            continue
        table_children = [
            child
            for child in candidates
            if child.tag == "table"
            and _is_selector_descendant(child.selector, candidate.selector)
            and _is_meaningful_child(child, candidate)
            and abs(child.y - candidate.y) <= 5
        ]
        if not table_children:
            output.append(candidate)
            continue
        child = max(table_children, key=lambda item: item.height)
        output.append(replace(candidate, x=child.x, y=child.y, width=child.width, height=child.height))
    return output


def _merge_visual_comparison_groups(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    merged: list[RawBlockCandidate] = []
    index = 0
    while index < len(candidates):
        candidate = candidates[index]
        if not _starts_comparison_group(candidates, index):
            merged.append(candidate)
            index += 1
            continue

        group = [candidate]
        bottom = candidate.bottom
        next_index = index + 1
        while next_index < len(candidates):
            next_candidate = candidates[next_index]
            gap = next_candidate.y - bottom
            if gap > 180:
                break
            if gap >= -30 and _belongs_to_comparison_group(next_candidate):
                group.append(next_candidate)
                bottom = max(bottom, next_candidate.bottom)
                next_index += 1
                continue
            break

        if len(group) == 1:
            merged.append(candidate)
            index += 1
            continue

        merged.append(_merge_candidates(group))
        index = next_index
    return merged


def _drop_large_visual_overlaps(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if candidate.selector == "body::first-view":
            output.append(candidate)
            continue
        if any(_is_large_visual_overlap(candidate, existing) for existing in output if existing.selector != "body::first-view"):
            continue
        output.append(candidate)
    return output


def _is_large_visual_overlap(candidate: RawBlockCandidate, existing: RawBlockCandidate) -> bool:
    if _is_selector_descendant(candidate.selector, existing.selector) or _is_selector_descendant(existing.selector, candidate.selector):
        return False
    if existing.height > OVERSIZED_PARENT_HEIGHT and _is_geometrically_inside(candidate, existing):
        return False
    if candidate.height > OVERSIZED_PARENT_HEIGHT and _is_geometrically_inside(existing, candidate):
        return False
    if _is_ranking_inner_detail_candidate(candidate) and _is_inside_ranking_scope(existing) and not _is_ranking_inner_detail_candidate(existing):
        return False
    vertical_overlap = min(candidate.bottom, existing.bottom) - max(candidate.y, existing.y)
    if vertical_overlap <= 0:
        return False
    overlap_ratio = vertical_overlap / max(1, min(candidate.height, existing.height))
    width_ratio = min(candidate.width, existing.width) / max(candidate.width, existing.width)
    if overlap_ratio < 0.7 or width_ratio < 0.85:
        return False
    candidate_words = set(candidate.text.split())
    existing_words = set(existing.text.split())
    if not candidate_words or not existing_words:
        return True
    text_overlap = len(candidate_words & existing_words) / max(1, min(len(candidate_words), len(existing_words)))
    return text_overlap >= 0.45


def _is_geometrically_inside(candidate: RawBlockCandidate, parent: RawBlockCandidate) -> bool:
    return candidate.y >= parent.y and candidate.bottom <= parent.bottom and candidate.x >= parent.x - 2 and candidate.x + candidate.width <= parent.x + parent.width + 2


def _merge_adjacent_ranking_ctas(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if not output:
            output.append(candidate)
            continue
        previous = output[-1]
        gap = candidate.y - previous.bottom
        if _is_rank_cta_candidate(candidate) and _can_merge_cta_into_previous(candidate, previous, gap):
            output[-1] = _merge_into_primary(previous, candidate)
            continue
        output.append(candidate)
    return output


def _can_merge_cta_into_previous(candidate: RawBlockCandidate, previous: RawBlockCandidate, gap: float) -> bool:
    if gap < 0 or gap > 140:
        return False
    if previous.selector == "body::first-view":
        return False
    if not _is_inside_ranking_scope(candidate) or not _is_inside_ranking_scope(previous):
        return False
    return candidate.height <= 90


def _merge_into_primary(primary: RawBlockCandidate, candidate: RawBlockCandidate) -> RawBlockCandidate:
    left = min(primary.x, candidate.x)
    top = min(primary.y, candidate.y)
    right = max(primary.x + primary.width, candidate.x + candidate.width)
    bottom = max(primary.bottom, candidate.bottom)
    text = " ".join([primary.text, candidate.text]).strip()
    class_name = " ".join(part for part in [primary.class_name, candidate.class_name] if part)
    return replace(
        primary,
        text=" ".join(text.split()),
        class_name=class_name,
        x=max(0, left),
        y=max(0, top),
        width=max(1, min(right - left, VIEWPORT["width"])),
        height=max(1, bottom - top),
    )


def _merge_wordpress_article_runs(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    output: list[RawBlockCandidate] = []
    index = 0
    while index < len(candidates):
        candidate = candidates[index]
        if not _is_wordpress_article_candidate(candidate):
            output.append(candidate)
            index += 1
            continue

        group = [candidate]
        bottom = candidate.bottom
        next_index = index + 1
        while next_index < len(candidates):
            next_candidate = candidates[next_index]
            gap = next_candidate.y - bottom
            max_gap = _wordpress_article_run_max_gap(group, next_candidate)
            if gap > max_gap:
                break
            if _is_wordpress_article_candidate(next_candidate) and _belongs_to_same_article_run(group, next_candidate):
                if _merged_candidate_height(group, next_candidate) > MAX_VIEWPORT_SCREENSHOT_HEIGHT - 200:
                    break
                group.append(next_candidate)
                bottom = max(bottom, next_candidate.bottom)
                next_index += 1
                continue
            break

        output.append(_merge_candidates(group) if len(group) > 1 else candidate)
        index = next_index
    return output


def _is_wordpress_article_candidate(candidate: RawBlockCandidate) -> bool:
    context = " ".join([candidate.selector, candidate.class_name, candidate.element_id])
    return _contains_any(context, ["main#main_content", "wp-block"])


def _belongs_to_same_article_run(group: list[RawBlockCandidate], candidate: RawBlockCandidate) -> bool:
    text = " ".join([item.text for item in group] + [candidate.text])
    if all(_is_wordpress_explainer_image_candidate(item) for item in [*group, candidate]):
        return True
    if _contains_any(text, ["スマイルモア矯正", "ウィ・スマイル", "ウィスマイル", "キレイライン矯正", "インビザライン"]):
        return True
    if _contains_any(text, ["選び方", "選ぶ理由", "失敗しない", "重要", "クリニック選び"]):
        return True
    return False


def _wordpress_article_run_max_gap(group: list[RawBlockCandidate], candidate: RawBlockCandidate) -> int:
    if all(_is_wordpress_explainer_image_candidate(item) for item in [*group, candidate]):
        return 450
    return 180


def _merged_candidate_height(group: list[RawBlockCandidate], candidate: RawBlockCandidate) -> float:
    top = min([item.y for item in group] + [candidate.y])
    bottom = max([item.bottom for item in group] + [candidate.bottom])
    return bottom - top


def _starts_comparison_group(candidates: list[RawBlockCandidate], index: int) -> bool:
    candidate = candidates[index]
    if candidate.selector == "body::first-view":
        return False
    if _is_per_item_comparison_card(candidate):
        return False
    if _is_ranking_candidate(candidate):
        return False
    if _is_cta_candidate(candidate):
        return False
    if _is_comparison_body_candidate(candidate):
        return True
    if not _is_comparison_heading_candidate(candidate):
        return False
    for next_candidate in candidates[index + 1 : index + 3]:
        if next_candidate.y - candidate.bottom > 180:
            break
        if _is_comparison_body_candidate(next_candidate):
            return True
    return False


def _belongs_to_comparison_group(candidate: RawBlockCandidate) -> bool:
    if _is_per_item_comparison_card(candidate):
        return False
    return _is_comparison_body_candidate(candidate) or _is_comparison_heading_candidate(candidate) or _is_cta_candidate(candidate)


def _is_comparison_body_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.tag, candidate.class_name, candidate.element_id, candidate.text])
    return (
        candidate.tag in {"table", "thead", "tbody"}
        or _contains_any(haystack, ["compare", "comparison", "hikaku", "top3", "比較表", "徹底比較", "横スクロール"])
        or _looks_like_comparison_matrix(candidate.text)
    )


def _is_comparison_heading_candidate(candidate: RawBlockCandidate) -> bool:
    if candidate.height > 220:
        return False
    if candidate.tag not in {"h1", "h2", "h3", "h4", "section", "div"}:
        return False
    haystack = " ".join([candidate.class_name, candidate.element_id, candidate.text])
    return _contains_any(haystack, ["compare", "comparison", "hikaku", "比較", "徹底比較"])


def _is_cta_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.class_name, candidate.element_id, candidate.text])
    return _contains_any(haystack, ["cta", "conversion", "公式サイト", "無料相談", "予約", "今すぐ", "詳細を見る", "こちら"])


def _is_per_item_comparison_card(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.class_name, candidate.element_id, candidate.text])
    return (
        candidate.tag == "div"
        and _contains_any(haystack, ["hikaku_table"])
        and _contains_any(haystack, ["料金プラン", "マウスピース種類", "医院数"])
    )


def _is_product_feature_card(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.class_name, candidate.element_id, candidate.text])
    return (
        candidate.tag == "div"
        and _contains_any(haystack, ["wp-block-sbd-checkpoint-block", "特徴"])
        and _contains_any(haystack, ["の特徴", "治療実績", "料金", "医院", "クリニック"])
    )


def _is_single_product_detail_table(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.element_id, candidate.text])
    if not _contains_any(haystack, ["料金プラン", "メーカー保証", "矯正範囲", "実績", "エリア"]):
        return False
    if _contains_any(haystack, ["1位", "2位", "3位"]) and _contains_any(haystack, ["比較表", "ランキング"]):
        return False
    labels = ["料金プラン", "メーカー保証", "矯正範囲", "実績", "エリア", "医院数"]
    return sum(1 for label in labels if label in haystack) >= 4


def _is_selection_criteria_candidate(candidate: RawBlockCandidate) -> bool:
    return _contains_any(candidate.text, ["選び方", "選ぶ理由", "失敗しない", "クリニック選び", "重要"])


def _is_wordpress_explainer_image_candidate(candidate: RawBlockCandidate) -> bool:
    context = " ".join([candidate.selector, candidate.class_name, candidate.element_id, candidate.text])
    return _is_wordpress_article_candidate(candidate) and _contains_any(context, ["wp-block-image", "<img", "wp-image"])


def _is_wordpress_product_detail_candidate(candidate: RawBlockCandidate) -> bool:
    return _is_wordpress_article_candidate(candidate) and _contains_any(
        candidate.text,
        ["スマイルモア矯正", "ウィ・スマイル", "ウィスマイル", "キレイライン矯正", "インビザライン", "月額", "特徴"],
    )


def _is_ranking_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.element_id, candidate.text])
    if _contains_any(haystack, ["ranking", "rank", "ランキング", "1位", "2位", "3位"]):
        return True
    return candidate.tag == "li" and _contains_any(haystack, ["基本情報", "料金プラン", "症例", "口コミ"])


def _is_ranking_basic_info_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    return (
        _is_inside_ranking_scope(candidate)
        and (
            (
                candidate.tag != "li"
                and _contains_any(haystack, ["div.wrap", "wrap"])
                and _contains_any(haystack, ["基本情報", "料金プラン", "費用目安", "初診料"])
            )
            or (
                candidate.tag == "table"
                and _contains_any(haystack, ["初回お試し", "通常価格", "口コミ", "治療法", "診療時間"])
            )
        )
    )


def _is_ranking_case_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    return (
        _is_inside_ranking_scope(candidate)
        and (candidate.tag == "dl" or _contains_any(" ".join([candidate.selector, candidate.class_name]), ["dl.case", "case"]))
        and _contains_any(haystack, ["症 例", "症例", "Before", "After"])
        and _contains_any(haystack, ["期間", "総額", "治療内容"])
    )


def _is_ranking_supported_type_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return (
        _is_inside_ranking_scope(candidate)
        and _contains_any(selector_context, ["div.check", "check"])
        and _contains_any(haystack, ["対応している歯並び"])
        and _contains_any(haystack, ["#すきっ歯", "#受け口", "#出っ歯", "ガタガタ"])
    )


def _is_ranking_point_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return (
        _is_inside_ranking_scope(candidate)
        and (candidate.tag == "dl" or _contains_any(selector_context, ["dl.point", "point", "recommendation"]))
        and _contains_any(haystack, ["おすすめポイント"])
        and _contains_any(haystack, ["満足度", "コスパ", "プレゼント", "おすすめ", "トライアル", "治療法", "専門"])
    )


def _is_ranking_location_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return (
        _is_inside_ranking_scope(candidate)
        and _contains_any(selector_context, ["location", "store"])
        and _contains_any(haystack, ["近くのクリニック", "店舗一覧", "関東", "関西"])
    )


def _is_review_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return _is_inside_ranking_scope(candidate) and _contains_any(selector_context, ["review"]) and _contains_any(haystack, ["口コミ", "⼝コミ", "★★★★★", "評判"])


def _is_limited_offer_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return _is_inside_ranking_scope(candidate) and _contains_any(selector_context, ["campaign"]) and _contains_any(haystack, ["限定", "初回", "off", "価格", "試せる"])


def _is_rank_cta_candidate(candidate: RawBlockCandidate) -> bool:
    haystack = " ".join([candidate.selector, candidate.class_name, candidate.text])
    selector_context = " ".join([candidate.selector, candidate.class_name])
    return _is_inside_ranking_scope(candidate) and _contains_any(selector_context, ["btn"]) and _contains_any(haystack, ["公式サイト", "チェック", "空き枠", "コチラ"])


def _is_inside_ranking_scope(candidate: RawBlockCandidate) -> bool:
    context = " ".join([candidate.selector, candidate.class_name, candidate.element_id])
    return _contains_any(context, ["ranking", "rank"])


def _is_ranking_inner_detail_candidate(candidate: RawBlockCandidate) -> bool:
    return (
        _is_ranking_basic_info_candidate(candidate)
        or _is_ranking_case_candidate(candidate)
        or _is_ranking_supported_type_candidate(candidate)
        or _is_ranking_point_candidate(candidate)
        or _is_ranking_location_candidate(candidate)
        or _is_review_candidate(candidate)
        or _is_limited_offer_candidate(candidate)
        or _is_rank_cta_candidate(candidate)
    )


def _has_ranking_detail_children(candidate: RawBlockCandidate, candidates: list[RawBlockCandidate]) -> bool:
    if not _is_inside_ranking_scope(candidate):
        return False
    if candidate.tag not in {"section", "div", "ul", "li"}:
        return False
    if _is_ranking_inner_detail_candidate(candidate):
        return False
    labels = ["基本情報", "料金プラン", "症 例", "症例", "対応している歯並び", "おすすめポイント", "近くのクリニック", "初回お試し", "口コミ", "キャンペーン", "店舗一覧"]
    if sum(1 for label in labels if label in candidate.text) < 2:
        return False
    detail_child_count = 0
    for child in candidates:
        if child is candidate:
            continue
        if not _is_ranking_inner_detail_candidate(child):
            continue
        if not _is_meaningful_child(child, candidate):
            continue
        detail_child_count += 1
        if detail_child_count >= 2:
            return True
    return False


def _drop_oversized_parents_with_children(candidates: list[RawBlockCandidate]) -> list[RawBlockCandidate]:
    output: list[RawBlockCandidate] = []
    for candidate in candidates:
        if _has_ranking_detail_children(candidate, candidates):
            continue
        if candidate.height > OVERSIZED_PARENT_HEIGHT and any(_is_meaningful_child(child, candidate) for child in candidates):
            continue
        output.append(candidate)
    return output


def _is_meaningful_child(candidate: RawBlockCandidate, parent: RawBlockCandidate) -> bool:
    if candidate is parent:
        return False
    if candidate.tag not in {"li", "div", "dl", "ul", "table", "section", "p"}:
        return False
    if candidate.y < parent.y or candidate.bottom > parent.bottom:
        return False
    width_ratio = candidate.width / max(parent.width, 1)
    return width_ratio >= 0.75 and candidate.height >= 120


def _merge_candidates(candidates: list[RawBlockCandidate]) -> RawBlockCandidate:
    left = min(candidate.x for candidate in candidates)
    top = min(candidate.y for candidate in candidates)
    right = max(candidate.x + candidate.width for candidate in candidates)
    bottom = max(candidate.bottom for candidate in candidates)
    text = " ".join(candidate.text for candidate in candidates if candidate.text)
    class_name = "hybrid-visual-block " + " ".join(candidate.class_name for candidate in candidates if candidate.class_name)
    return RawBlockCandidate(
        selector="hybrid::comparison",
        tag="section",
        text=" ".join(text.split()),
        x=max(0, left),
        y=max(0, top),
        width=max(1, min(right - left, VIEWPORT["width"])),
        height=max(1, bottom - top),
        class_name=class_name,
        element_id="",
    )


def _is_nested_duplicate(candidate: RawBlockCandidate, existing: RawBlockCandidate) -> bool:
    if candidate.y < existing.y or candidate.bottom > existing.bottom:
        return False
    vertical_overlap = min(candidate.bottom, existing.bottom) - max(candidate.y, existing.y)
    if vertical_overlap <= 0:
        return False
    width_ratio = min(candidate.width, existing.width) / max(candidate.width, existing.width)
    height_ratio = candidate.height / existing.height
    if _is_selector_descendant(candidate.selector, existing.selector):
        return True
    if width_ratio >= 0.9 and abs(candidate.y - existing.y) <= 3 and abs(candidate.bottom - existing.bottom) <= 3:
        return True
    if width_ratio >= 0.9 and abs(candidate.y - existing.y) <= 3 and height_ratio >= 0.75:
        return True
    child_tag = candidate.tag in {"table", "tr", "td", "th", "tbody", "thead", "li", "a", "button", "figure"}
    return width_ratio >= 0.75 and (child_tag or height_ratio <= 0.85)


def _is_selector_descendant(candidate_selector: str, existing_selector: str) -> bool:
    if not candidate_selector or not existing_selector:
        return False
    if "::" in candidate_selector or "::" in existing_selector:
        return False
    return candidate_selector.startswith(existing_selector + " > ")


def _looks_like_comparison_matrix(text: str) -> bool:
    labels = ["矯正費用", "初診料", "再診料", "治療期間", "提携院数", "費用目安", "料金プラン"]
    return sum(1 for label in labels if label in text) >= 2


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0] or "unknown"


def _safe_slug(text: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "-", text).strip("-")
    return normalized[:80] or "block"


def _truncate(text: str, max_length: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def review_captured_blocks(blocks: list[CapturedBlock]) -> list[str]:
    warnings: list[str] = []
    by_url: dict[str, list[CapturedBlock]] = {}
    for block in blocks:
        by_url.setdefault(block.source_url, []).append(block)

    for source_url, url_blocks in by_url.items():
        non_fv = [block for block in url_blocks if block.detail_label != "ファーストビュー結論"]
        for index, block in enumerate(non_fv):
            for other in non_fv[index + 1 :]:
                if _captured_selectors_are_nested(block.selector, other.selector):
                    continue
                overlap = min(block.clip["y"] + block.clip["height"], other.clip["y"] + other.clip["height"]) - max(block.clip["y"], other.clip["y"])
                if overlap <= 0:
                    continue
                ratio = overlap / max(1, min(block.clip["height"], other.clip["height"]))
                if ratio >= 0.7:
                    warnings.append(f"overlap: {source_url} order {block.order} and {other.order} overlap by {ratio:.0%}")

        tiny_ctas = [block for block in url_blocks if block.detail_label == "CTA反復" and block.clip["height"] <= 90]
        if len(tiny_ctas) >= 3:
            orders = ", ".join(str(block.order) for block in tiny_ctas)
            warnings.append(f"tiny CTA: {source_url} has {len(tiny_ctas)} CTA-only blocks at orders {orders}")

        comparison_like_product = [
            block
            for block in url_blocks
            if block.detail_label == "一括比較表"
            and all(label in block.structure_memo for label in ["料金プラン", "矯正範囲", "エリア"])
        ]
        if comparison_like_product:
            orders = ", ".join(str(block.order) for block in comparison_like_product)
            warnings.append(f"single product mislabeled as comparison: {source_url} orders {orders}")

    return warnings


def _captured_selectors_are_nested(first: str, second: str) -> bool:
    return _is_selector_descendant(first, second) or _is_selector_descendant(second, first)
