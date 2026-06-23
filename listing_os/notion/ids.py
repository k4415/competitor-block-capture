from __future__ import annotations

import re


NOTION_ID_PATTERN = re.compile(r"([0-9a-fA-F]{32})")


def normalize_notion_id(value: str) -> str:
    text = (value or "").strip()
    matches = NOTION_ID_PATTERN.findall(text)
    compact = matches[-1] if matches else text.replace("-", "")
    if len(compact) != 32 or not re.fullmatch(r"[0-9a-fA-F]{32}", compact):
        return text
    compact = compact.lower()
    return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"
