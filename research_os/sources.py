from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib import request

from .models import SourceDocument


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f"画像alt: {alt}")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self.in_title:
            self.title_parts.append(cleaned)
        self.parts.append(cleaned)

    def document(self, url: str, fallback_title: str = "") -> SourceDocument:
        title = " ".join(self.title_parts).strip() or fallback_title or url
        text = _clean_text(" ".join(self.parts))
        return SourceDocument(url=url, title=html.unescape(title), text=html.unescape(text))


def fetch_url(url: str, timeout: int = 20) -> SourceDocument:
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 research-os/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.document(url)


def load_source_documents(path: str | Path) -> list[SourceDocument]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    docs = payload if isinstance(payload, list) else payload.get("documents", [])
    return [SourceDocument(url=item["url"], title=item.get("title", item["url"]), text=item.get("text", "")) for item in docs]


def fetch_many(urls: Iterable[str]) -> list[SourceDocument]:
    docs = []
    for url in urls:
        try:
            docs.append(fetch_url(url))
        except Exception as error:  # noqa: BLE001 - keep batch jobs moving with a source stub.
            docs.append(SourceDocument(url=url, title=url, text=f"取得失敗: {error}"))
    return docs


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
