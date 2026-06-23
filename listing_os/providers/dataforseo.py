from __future__ import annotations

import base64
import json
from typing import Any
from urllib import request


DATAFORSEO_SERP_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
DATAFORSEO_KEYWORD_VOLUME_ENDPOINT = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"


class DataForSeoClient:
    def __init__(self, login: str, password: str, timeout: int = 60) -> None:
        self.login = login
        self.password = password
        self.timeout = timeout

    def collect_serp(
        self,
        *,
        keyword: str,
        location_code: int = 2392,
        language_code: str = "ja",
        device: str = "mobile",
        depth: int = 10,
        tag: str | None = None,
    ) -> dict[str, Any]:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device,
                "depth": depth,
                **({"tag": tag} if tag else {}),
            }
        ]
        return self._post(DATAFORSEO_SERP_ENDPOINT, payload)

    def search_volume(
        self,
        *,
        keywords: list[str],
        location_code: int = 2392,
        language_code: str = "ja",
        search_partners: bool = False,
    ) -> dict[str, Any]:
        payload = [
            {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code,
                "search_partners": search_partners,
            }
        ]
        return self._post(DATAFORSEO_KEYWORD_VOLUME_ENDPOINT, payload)

    def _post(self, url: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        credentials = base64.b64encode(f"{self.login}:{self.password}".encode("utf-8")).decode("ascii")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def parse_serp_response(response: dict[str, Any], *, genre_id: str, query: str) -> dict[str, Any]:
    tasks = response.get("tasks") or []
    items: list[dict[str, Any]] = []
    if tasks:
        for result in tasks[0].get("result") or []:
            for item in result.get("items") or []:
                url = item.get("url") or item.get("breadcrumb")
                if not url:
                    continue
                items.append(
                    {
                        "rank": item.get("rank_absolute") or item.get("rank_group") or 999,
                        "type": "paid" if item.get("type") in {"paid", "google_ads"} else "organic",
                        "url": url,
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                    }
                )
    return {"genre_id": genre_id, "query": query, "results": items}
