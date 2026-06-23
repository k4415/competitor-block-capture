from __future__ import annotations

from pathlib import Path
from typing import Iterable

from research_os.models import SourceDocument
from research_os.sources import fetch_many


def fetch_rendered_competitor_documents(urls: Iterable[str], *, artifact_dir: str | Path = "artifacts/research-os-v2/screenshots") -> list[SourceDocument]:
    url_list = list(urls)
    if not url_list:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 - Playwright is optional; HTML fetch remains the fallback.
        return fetch_many(url_list)

    docs: list[SourceDocument] = []
    screenshot_dir = Path(artifact_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 1200}, user_agent="Mozilla/5.0 research-os-v2")
            for index, url in enumerate(url_list, start=1):
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    title = page.title() or url
                    body_text = page.locator("body").inner_text(timeout=5000)
                    image_alts = page.eval_on_selector_all("img", "(imgs) => imgs.map((img) => img.alt || img.getAttribute('aria-label') || '').filter(Boolean).join('\\n')")
                    screenshot = screenshot_dir / f"competitor-{index}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    rendered_text = "\n".join(part for part in [body_text, f"画像alt:\n{image_alts}" if image_alts else "", f"スクリーンショット: {screenshot}"] if part)
                    docs.append(SourceDocument(url=url, title=title, text=rendered_text))
                except Exception as error:  # noqa: BLE001 - keep batch jobs moving.
                    docs.append(SourceDocument(url=url, title=url, text=f"取得失敗: {error}"))
            browser.close()
    except Exception:  # noqa: BLE001 - fallback if browser launch is unavailable.
        return fetch_many(url_list)
    return docs
