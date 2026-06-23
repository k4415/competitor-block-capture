from __future__ import annotations

import json
import re
from pathlib import Path


PAGE_ID_PATTERN = re.compile(r"([0-9a-f]{32})", re.IGNORECASE)


def discover_v1_page_ids(paths: list[str] | None = None) -> list[str]:
    candidates = [Path(path) for path in paths] if paths else [
        Path("artifacts/research-os-marriage-agency-run.json"),
        Path("artifacts/research-os-run-result.json"),
        Path("artifacts/research-os-ui-post.html"),
    ]
    page_ids: list[str] = []
    for path in candidates:
        if not path.exists() or "v2" in path.name:
            continue
        page_ids.extend(_extract_page_ids(path))
    return _dedupe(page_ids)


def _extract_page_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        page_id = payload.get("category_page_id") or payload.get("parent_page_id")
        if isinstance(page_id, str) and page_id:
            return [_format_page_id(page_id)]
    return [_format_page_id(match.group(1)) for match in PAGE_ID_PATTERN.finditer(text)]


def _format_page_id(value: str) -> str:
    compact = value.replace("-", "")
    if len(compact) != 32:
        return value
    return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
