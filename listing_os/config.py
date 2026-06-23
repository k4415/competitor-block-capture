from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ListingOsConfig:
    notion_parent_page_id: str
    default_location_code: int = 2392
    default_language_code: str = "ja"
    default_device: str = "mobile"
    dataforseo_login: str | None = None
    dataforseo_password: str | None = None


def load_config(path: str | Path | None = None) -> ListingOsConfig:
    raw: dict[str, Any] = {}
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ListingOsConfig(
        notion_parent_page_id=raw.get("notion_parent_page_id") or os.getenv("NOTION_PARENT_PAGE_ID", ""),
        default_location_code=int(raw.get("default_location_code") or os.getenv("DEFAULT_LOCATION_CODE", "2392")),
        default_language_code=raw.get("default_language_code") or os.getenv("DEFAULT_LANGUAGE_CODE", "ja"),
        default_device=raw.get("default_device") or os.getenv("DEFAULT_DEVICE", "mobile"),
        dataforseo_login=raw.get("dataforseo_login") or os.getenv("DATAFORSEO_LOGIN"),
        dataforseo_password=raw.get("dataforseo_password") or os.getenv("DATAFORSEO_PASSWORD"),
    )
