from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .normalization import normalize_domain, normalize_url


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*([^\s]+)"),
    re.compile(r"(?i)(authorization:\s*bearer)\s+([^\s]+)"),
]


def analyze_serp_snapshot(snapshot: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    results = snapshot.get("results", [])
    for result in results:
        url = result.get("url", "")
        if not url:
            continue
        domain = normalize_domain(url)
        enriched = dict(result)
        enriched["url"] = normalize_url(url)
        enriched["domain"] = domain
        grouped[domain].append(enriched)

    competitor_sites = [_summarize_domain(domain, items) for domain, items in grouped.items()]
    competitor_sites.sort(key=lambda item: (-item["score"], item["best_rank"], item["domain"]))
    limited_sites = competitor_sites[:limit]
    return {
        "genre_id": snapshot.get("genre_id", ""),
        "query": snapshot.get("query", ""),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "competitor_sites": limited_sites,
        "stats": {
            "raw_results": len(results),
            "unique_domains": len(competitor_sites),
            "returned_domains": len(limited_sites),
        },
    }


def generate_vendor_brief(
    *,
    genre_id: str,
    genre_name: str,
    analysis: dict[str, Any],
    offers: list[dict[str, Any]],
    internal_notes: str = "",
) -> str:
    top_sites = analysis.get("competitor_sites", [])[:10]
    offer_lines = [
        f"- {offer.get('name', '未命名案件')}: 報酬 {offer.get('commission', '未確認')} / 承認条件 {offer.get('approval_terms', '未確認')}"
        for offer in offers
    ] or ["- 未登録: ASP/代理店から入稿後に追記"]
    site_lines = [
        f"- {site['domain']} rank {site['best_rank']} score {site['score']}: {site.get('title', '')} ({site.get('url', '')})"
        for site in top_sites
    ] or ["- 競合未取得: SERP収集後に追記"]
    axis_candidates = _ranking_axes_from_sites(top_sites)
    sections = [
        f"# 外注指示パック: {genre_name}",
        "",
        f"- Genre ID: {genre_id}",
        f"- Generated At: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 目的",
        f"{genre_name} の比較リス案件を立ち上げるため、比較LPの構成、原稿骨子、制作注意点を外注先に共有する。",
        "",
        "## 競合観察",
        *site_lines,
        "",
        "## ASP/案件候補",
        *offer_lines,
        "",
        "## 比較LP構成案",
        "1. ファーストビュー: ジャンル名、選び方、主要CTA",
        "2. 比較表: " + " / ".join(axis_candidates),
        "3. おすすめランキング: 案件ごとの向き不向き、根拠、CTA",
        "4. 判断基準: 料金、実績、口コミ、保証、通いやすさなど",
        "5. FAQ: 不安、審査、費用、期間、リスクを先回りして回答",
        "",
        "## ランキング軸",
        *[f"- {axis}" for axis in axis_candidates],
        "",
        "## 制作注意点",
        "- 広告審査に抵触しやすい断定表現、過度なNo.1表現、未確認の実績表現は使わない。",
        "- 競合の見出しや本文をコピーせず、構造と判断軸だけを参考にする。",
        "- 未確認の数値、症例、口コミ、権威性はNotionの案件DBで確認できるものだけ使う。",
        "",
        "## 検収条件",
        "- 比較表、ランキング、FAQ、CTAが実装されている。",
        "- スマホ表示でFV、比較表、CTAが崩れていない。",
        "- 外注先に渡してはいけないAPIキー、内部メモ、個人情報が含まれていない。",
    ]
    if internal_notes:
        sections.extend(["", "## Internal Notes Removed", sanitize_for_vendor(internal_notes)])
    return sanitize_for_vendor("\n".join(sections).strip() + "\n")


def export_vendor_pack(brief_markdown: str, output_dir: Path | str, pack_id: str) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    brief_path = output_path / "brief.md"
    manifest_path = output_path / "manifest.json"
    brief_path.write_text(sanitize_for_vendor(brief_markdown), encoding="utf-8")
    manifest = {
        "pack_id": pack_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": ["brief.md"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"brief_path": brief_path, "manifest_path": manifest_path}


def sanitize_for_vendor(text: str) -> str:
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def _summarize_domain(domain: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [int(item.get("rank", 999)) for item in items]
    best = min(ranks)
    types = {item.get("type", "organic") for item in items}
    representative = sorted(items, key=lambda item: int(item.get("rank", 999)))[0]
    score = max(0, 100 - best * 6) + max(0, len(items) - 1) * 8
    if "paid" in types:
        score += 10
    return {
        "domain": domain,
        "url": representative.get("url", ""),
        "title": representative.get("title", ""),
        "description": representative.get("description", ""),
        "best_rank": best,
        "appearances": len(items),
        "type": "mixed" if len(types) > 1 else next(iter(types)),
        "score": min(100, score),
    }


def _ranking_axes_from_sites(sites: list[dict[str, Any]]) -> list[str]:
    text = " ".join(f"{site.get('title', '')} {site.get('description', '')}" for site in sites)
    axes = []
    candidates = {
        "料金": ["料金", "価格", "費用", "安い"],
        "実績": ["実績", "症例", "導入", "件数"],
        "口コミ": ["口コミ", "評判", "レビュー"],
        "保証": ["保証", "返金", "安心"],
        "通いやすさ": ["店舗", "通い", "エリア", "オンライン"],
    }
    for axis, keywords in candidates.items():
        if any(keyword in text for keyword in keywords):
            axes.append(axis)
    for fallback in ["料金", "実績", "口コミ", "サポート", "CTA条件"]:
        if fallback not in axes:
            axes.append(fallback)
        if len(axes) >= 5:
            break
    return axes[:5]
