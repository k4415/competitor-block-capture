from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from .block_models import CapturedBlock
from .block_notion import resolve_block_data_source_id


REFERENCE_STATUS_TO_NOTION = {
    "ok": "OK",
    "needs_review": "要確認",
    "no_reference": "参照なし",
}


@dataclass(frozen=True)
class ReferenceReviewResult:
    status: str
    reference_strength: str
    similarity_score: float
    warnings: tuple[str, ...] = ()
    suggested_fixes: tuple[str, ...] = ()
    reference_run_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        payload["suggested_fixes"] = list(self.suggested_fixes)
        payload["reference_run_ids"] = list(self.reference_run_ids)
        return payload


def no_reference_review() -> ReferenceReviewResult:
    return ReferenceReviewResult(status="no_reference", reference_strength="none", similarity_score=0.0)


def load_reference_blocks_from_notion(
    *,
    notion: object,
    database_id: str,
    urls: Iterable[str],
    category_name: str,
    viewport: str,
    page_size: int = 100,
) -> list[CapturedBlock]:
    data_source_id = resolve_block_data_source_id(notion=notion, database_id=database_id)
    queries = _reference_query_payloads(urls=list(urls), category_name=category_name, viewport=viewport, page_size=page_size)
    pages: dict[str, dict[str, Any]] = {}
    for payload in queries:
        for page in _query_all_pages(notion=notion, data_source_id=data_source_id, payload=payload):
            page_id = str(page.get("id", ""))
            if page_id:
                pages[page_id] = page
    return [block for block in (_captured_block_from_notion_page(page) for page in pages.values()) if block is not None]


def review_blocks_against_references(
    current_blocks: list[CapturedBlock],
    reference_blocks: list[CapturedBlock],
    *,
    category_name: str,
) -> ReferenceReviewResult:
    current_by_url = _group_by_url([block for block in current_blocks if block.status == "取得済み"])
    if not current_by_url or not reference_blocks:
        return no_reference_review()

    scores: list[float] = []
    warnings: list[str] = []
    fixes: list[str] = []
    reference_run_ids: list[str] = []
    strengths: list[str] = []

    for source_url, url_blocks in current_by_url.items():
        selected_refs, strength = _select_reference_blocks_for_url(source_url, reference_blocks, category_name=category_name)
        if not selected_refs:
            warnings.append(f"no_reference_for_url: {source_url}")
            fixes.append("同一URLまたは同一ドメインの承認済み参照ブロックを追加してください")
            continue
        best_group = _best_reference_group(url_blocks, selected_refs)
        if not best_group:
            warnings.append(f"no_reference_for_url: {source_url}")
            continue
        score = _block_group_similarity(url_blocks, best_group)
        scores.append(score)
        strengths.append(strength)
        reference_run_ids.extend(block.run_id for block in best_group if block.run_id)
        group_warnings, group_fixes = _review_block_group(source_url, url_blocks, best_group, score)
        warnings.extend(group_warnings)
        fixes.extend(group_fixes)

    if not scores:
        return no_reference_review()

    similarity_score = round(sum(scores) / len(scores), 3)
    unique_warnings = tuple(_dedupe(warnings))
    status = "needs_review" if unique_warnings or similarity_score < 0.7 else "ok"
    return ReferenceReviewResult(
        status=status,
        reference_strength=_strongest_reference_strength(strengths),
        similarity_score=similarity_score,
        warnings=unique_warnings,
        suggested_fixes=tuple(_dedupe(fixes)),
        reference_run_ids=tuple(_dedupe(reference_run_ids)),
    )


def apply_reference_review_to_blocks(blocks: list[CapturedBlock], review: ReferenceReviewResult) -> list[CapturedBlock]:
    notion_status = REFERENCE_STATUS_TO_NOTION.get(review.status, "参照なし")
    note_parts = [*review.warnings, *review.suggested_fixes]
    note = " / ".join(_dedupe(note_parts))
    similarity = review.similarity_score if review.reference_strength != "none" else None
    return [
        replace(
            block,
            reference_review_status=notion_status,
            reference_similarity=similarity,
            reference_review_note=note,
            reference_run_ids=review.reference_run_ids,
        )
        for block in blocks
    ]


def _reference_query_payloads(*, urls: list[str], category_name: str, viewport: str, page_size: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    cleaned_urls = [url for url in urls if url]
    if cleaned_urls:
        payloads.append(_query_payload(_and_filter([_or_filter([_url_filter(url) for url in cleaned_urls]), _viewport_filter(viewport), _status_filter()]), page_size))

    domains = _dedupe(_domain_from_url(url) for url in cleaned_urls if url)
    if domains:
        payloads.append(_query_payload(_and_filter([_or_filter([_rich_text_contains_filter("ドメイン", domain) for domain in domains]), _viewport_filter(viewport), _status_filter()]), page_size))

    if category_name:
        payloads.append(_query_payload(_and_filter([_title_contains_filter("名前", category_name), _viewport_filter(viewport), _status_filter()]), page_size))
    return payloads


def _query_payload(filter_payload: dict[str, Any], page_size: int) -> dict[str, Any]:
    return {
        "filter": filter_payload,
        "sorts": [{"property": "ブロック順", "direction": "ascending"}],
        "page_size": page_size,
    }


def _query_all_pages(*, notion: object, data_source_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    next_cursor = None
    while True:
        page_payload = dict(payload)
        if next_cursor:
            page_payload["start_cursor"] = next_cursor
        response = notion.query_data_source(data_source_id, page_payload)
        output.extend(response.get("results", []))
        if not response.get("has_more"):
            return output
        next_cursor = response.get("next_cursor")
        if not next_cursor:
            return output


def _captured_block_from_notion_page(page: dict[str, Any]) -> CapturedBlock | None:
    props = page.get("properties") or {}
    source_url = _url_prop(props.get("元URL"))
    if not source_url:
        return None
    clip = _json_prop(props.get("スクショ範囲")) or {"x": 0, "y": 0, "width": 390, "height": 1}
    return CapturedBlock(
        name=_text_prop(props.get("名前")) or source_url,
        source_url=source_url,
        domain=_text_prop(props.get("ドメイン")) or _domain_from_url(source_url),
        page_title=_text_prop(props.get("ページタイトル")),
        run_id=_text_prop(props.get("Run ID")) or str(page.get("id", "")),
        viewport=_select_prop(props.get("表示幅")) or "mobile-390",
        order=int(_number_prop(props.get("ブロック順")) or 0),
        major_category=_select_prop(props.get("ブロック大分類")) or "その他",
        detail_label=_select_prop(props.get("詳細ラベル")) or "その他",
        screenshot_path="",
        structure_memo=_text_prop(props.get("構造メモ")),
        image_prompt=_text_prop(props.get("画像生成プロンプト")),
        prompt_state=_select_prop(props.get("プロンプト状態")) or "未生成",
        confidence=_select_prop(props.get("信頼度")) or "低",
        extracted_at=_date_prop(props.get("抽出日時")) or datetime.now(timezone.utc).isoformat(),
        clip=clip,
        selector="",
        status=_select_prop(props.get("ステータス")) or "取得済み",
    )


def _select_reference_blocks_for_url(source_url: str, references: list[CapturedBlock], *, category_name: str) -> tuple[list[CapturedBlock], str]:
    domain = _domain_from_url(source_url)
    exact = [block for block in references if block.source_url == source_url]
    if exact:
        return exact, "exact_url"
    same_domain = [block for block in references if block.domain == domain]
    if same_domain:
        return same_domain, "same_domain"
    same_category = [block for block in references if category_name and category_name in block.name]
    if same_category:
        return same_category, "same_category"
    return [], "none"


def _best_reference_group(current: list[CapturedBlock], references: list[CapturedBlock]) -> list[CapturedBlock]:
    groups = _group_by_run_and_url(references)
    if not groups:
        return []
    return max(groups, key=lambda group: _block_group_similarity(current, group))


def _review_block_group(source_url: str, current: list[CapturedBlock], reference: list[CapturedBlock], score: float) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    fixes: list[str] = []
    current_count = len(current)
    reference_count = len(reference)
    count_diff = current_count - reference_count
    drift_threshold = max(3, int(max(reference_count, 1) * 0.45))

    if abs(count_diff) >= drift_threshold:
        if count_diff < 0:
            warnings.append(f"over_merged: {source_url} has {current_count} blocks; reference has {reference_count}")
            fixes.append("ランキング本文や個別候補詳細が大きな親ブロックにまとまり過ぎていないか確認してください")
        else:
            warnings.append(f"over_split: {source_url} has {current_count} blocks; reference has {reference_count}")
            fixes.append("比較表や解説ブロックが細かく分割され過ぎていないか確認してください")

    if score < 0.55:
        warnings.append(f"label_sequence_drift: {source_url} similarity={score:.2f}")
        fixes.append("参照DBの詳細ラベル順と大きく違うため、区切り順と分類ラベルを確認してください")

    missing_flow = _missing_flow_labels(current, reference)
    if missing_flow:
        warnings.append(f"flow_drift: {source_url} missing {', '.join(missing_flow)}")
        fixes.append("ファーストビュー、比較表、ランキング、FAQ、CTAの主要導線が欠けていないか確認してください")

    mislabeled = [block.order for block in current if _looks_like_single_product_mislabeled_as_comparison(block)]
    if mislabeled:
        warnings.append(f"single_product_mislabeled_as_comparison: {source_url} orders {', '.join(str(order) for order in mislabeled)}")
        fixes.append("1商品ごとの詳細表は一括比較表ではなく個別候補詳細として扱ってください")

    return warnings, fixes


def _block_group_similarity(current: list[CapturedBlock], reference: list[CapturedBlock]) -> float:
    if not current or not reference:
        return 0.0
    current_labels = [block.detail_label for block in sorted(current, key=lambda block: block.order)]
    reference_labels = [block.detail_label for block in sorted(reference, key=lambda block: block.order)]
    sequence_score = _lcs_ratio(current_labels, reference_labels)
    count_score = min(len(current_labels), len(reference_labels)) / max(len(current_labels), len(reference_labels))
    return round((sequence_score * 0.7) + (count_score * 0.3), 3)


def _lcs_ratio(first: list[str], second: list[str]) -> float:
    if not first or not second:
        return 0.0
    rows = len(first) + 1
    cols = len(second) + 1
    table = [[0] * cols for _ in range(rows)]
    for row in range(1, rows):
        for col in range(1, cols):
            if first[row - 1] == second[col - 1]:
                table[row][col] = table[row - 1][col - 1] + 1
            else:
                table[row][col] = max(table[row - 1][col], table[row][col - 1])
    return table[-1][-1] / max(len(first), len(second))


def _missing_flow_labels(current: list[CapturedBlock], reference: list[CapturedBlock]) -> list[str]:
    flow_labels = ["ファーストビュー結論", "一括比較表", "ランキング本文", "FAQ/Q&A", "CTA反復"]
    current_labels = {block.detail_label for block in current}
    reference_labels = {block.detail_label for block in reference}
    return [label for label in flow_labels if label in reference_labels and label not in current_labels]


def _looks_like_single_product_mislabeled_as_comparison(block: CapturedBlock) -> bool:
    if block.detail_label != "一括比較表":
        return False
    memo = block.structure_memo
    return all(label in memo for label in ["料金プラン", "矯正範囲", "エリア"])


def _group_by_url(blocks: list[CapturedBlock]) -> dict[str, list[CapturedBlock]]:
    grouped: dict[str, list[CapturedBlock]] = {}
    for block in blocks:
        grouped.setdefault(block.source_url, []).append(block)
    return {key: sorted(value, key=lambda block: block.order) for key, value in grouped.items()}


def _group_by_run_and_url(blocks: list[CapturedBlock]) -> list[list[CapturedBlock]]:
    grouped: dict[tuple[str, str], list[CapturedBlock]] = {}
    for block in blocks:
        grouped.setdefault((block.run_id, block.source_url), []).append(block)
    return [sorted(value, key=lambda block: block.order) for value in grouped.values()]


def _strongest_reference_strength(strengths: list[str]) -> str:
    rank = {"none": 0, "same_category": 1, "same_domain": 2, "exact_url": 3}
    return max(strengths or ["none"], key=lambda value: rank.get(value, 0))


def _and_filter(filters: list[dict[str, Any]]) -> dict[str, Any]:
    return {"and": filters}


def _or_filter(filters: list[dict[str, Any]]) -> dict[str, Any]:
    return {"or": filters}


def _url_filter(url: str) -> dict[str, Any]:
    return {"property": "元URL", "url": {"equals": url}}


def _viewport_filter(viewport: str) -> dict[str, Any]:
    return {"property": "表示幅", "select": {"equals": viewport}}


def _status_filter() -> dict[str, Any]:
    return {"property": "ステータス", "select": {"equals": "取得済み"}}


def _rich_text_contains_filter(property_name: str, text: str) -> dict[str, Any]:
    return {"property": property_name, "rich_text": {"contains": text}}


def _title_contains_filter(property_name: str, text: str) -> dict[str, Any]:
    return {"property": property_name, "title": {"contains": text}}


def _text_prop(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    parts: list[str] = []
    for key in ("title", "rich_text"):
        for item in prop.get(key) or []:
            parts.append(str(item.get("plain_text") or (item.get("text") or {}).get("content") or ""))
    return " ".join(part for part in parts if part).strip()


def _url_prop(prop: dict[str, Any] | None) -> str:
    return str((prop or {}).get("url") or "")


def _number_prop(prop: dict[str, Any] | None) -> float | None:
    value = (prop or {}).get("number")
    return float(value) if isinstance(value, (int, float)) else None


def _select_prop(prop: dict[str, Any] | None) -> str:
    selected = (prop or {}).get("select") or {}
    return str(selected.get("name") or "")


def _date_prop(prop: dict[str, Any] | None) -> str:
    date = (prop or {}).get("date") or {}
    return str(date.get("start") or "")


def _json_prop(prop: dict[str, Any] | None) -> dict[str, float] | None:
    text = _text_prop(prop)
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return {key: float(value.get(key, 0)) for key in ("x", "y", "width", "height")}


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0] or "unknown"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
