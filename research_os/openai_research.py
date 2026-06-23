from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from .models import CompetitorSiteRecord, PlayerRecord, ResearchBundle, ResearchFact


RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIResearchClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 120) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    def research(self, *, category_name: str, memo: str, competitor_urls: list[str], depth: str, research_run_id: str) -> ResearchBundle:
        if not self.available():
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI research")
        prompt = (
            "日本語で比較リスティング広告用のリサーチを実行してください。"
            "出力はJSON schemaに厳密準拠。1 fact = 1 row。"
            "Source URLがない事実は出さない。引用は短く、本文丸ごとの転載は禁止。"
            f"\nCategory: {category_name}\nMemo: {memo}\nDepth: {depth}\nCompetitor URLs:\n"
            + "\n".join(competitor_urls)
        )
        response = self._post(
            {
                "model": self.model,
                "input": prompt,
                "tools": [{"type": os.getenv("OPENAI_WEB_SEARCH_TOOL", "web_search_preview")}],
                "text": {"format": {"type": "json_schema", "name": "research_bundle", "schema": _bundle_schema(), "strict": True}},
            }
        )
        return _bundle_from_payload(_extract_json(response), research_run_id)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            RESPONSES_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _extract_json(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("output_text"):
        return json.loads(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return json.loads(text)
    raise RuntimeError("OpenAI response did not contain JSON text")


def _bundle_from_payload(payload: dict[str, Any], research_run_id: str) -> ResearchBundle:
    return ResearchBundle(
        category_facts=[_fact("category", item, research_run_id) for item in payload.get("category_facts", [])],
        target_facts=[_fact("target", item, research_run_id) for item in payload.get("target_facts", [])],
        players=[
            PlayerRecord(
                player_name=item.get("player_name", ""),
                source_url=item.get("source_url", ""),
                source_title=item.get("source_title", ""),
                evidence_snippet=item.get("evidence_snippet", ""),
                research_run_id=research_run_id,
                price=item.get("price", ""),
                plan=item.get("plan", ""),
                members=item.get("members", ""),
                results=item.get("results", ""),
                offer=item.get("offer", ""),
                official_url=item.get("official_url", ""),
                features=item.get("features", []),
                confidence=item.get("confidence", "Medium"),
            )
            for item in payload.get("players", [])
        ],
        competitors=[
            CompetitorSiteRecord(
                url=item.get("url", ""),
                domain=item.get("domain", ""),
                source_title=item.get("source_title", ""),
                structure_type=item.get("structure_type", "Unknown"),
                rankings=item.get("rankings", []),
                main_cta=item.get("main_cta", ""),
                listed_players=item.get("listed_players", []),
                direct_competitor=bool(item.get("direct_competitor", False)),
                evidence_snippet=item.get("evidence_snippet", ""),
                full_transcript_summary=item.get("full_transcript_summary", ""),
                confidence=item.get("confidence", "Medium"),
                research_run_id=research_run_id,
            )
            for item in payload.get("competitors", [])
        ],
    )


def _fact(table: str, item: dict[str, Any], research_run_id: str) -> ResearchFact:
    return ResearchFact(
        table=table,
        fact=item.get("fact", ""),
        category=item.get("category", ""),
        source_url=item.get("source_url", ""),
        source_title=item.get("source_title", ""),
        evidence_snippet=item.get("evidence_snippet", ""),
        confidence=item.get("confidence", "Medium"),
        research_run_id=research_run_id,
    )


def _bundle_schema() -> dict[str, Any]:
    fact = {
        "type": "object",
        "additionalProperties": False,
        "required": ["fact", "category", "source_url", "source_title", "evidence_snippet", "confidence"],
        "properties": {
            "fact": {"type": "string"},
            "category": {"type": "string"},
            "source_url": {"type": "string"},
            "source_title": {"type": "string"},
            "evidence_snippet": {"type": "string"},
            "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
        },
    }
    player = {
        "type": "object",
        "additionalProperties": False,
        "required": ["player_name", "source_url", "source_title", "evidence_snippet", "confidence"],
        "properties": {
            "player_name": {"type": "string"},
            "source_url": {"type": "string"},
            "source_title": {"type": "string"},
            "evidence_snippet": {"type": "string"},
            "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
            "price": {"type": "string"},
            "plan": {"type": "string"},
            "members": {"type": "string"},
            "results": {"type": "string"},
            "offer": {"type": "string"},
            "official_url": {"type": "string"},
            "features": {"type": "array", "items": {"type": "string"}},
        },
    }
    competitor = {
        "type": "object",
        "additionalProperties": False,
        "required": ["url", "domain", "source_title", "structure_type", "rankings", "main_cta", "listed_players", "direct_competitor", "evidence_snippet", "confidence"],
        "properties": {
            "url": {"type": "string"},
            "domain": {"type": "string"},
            "source_title": {"type": "string"},
            "structure_type": {"type": "string"},
            "rankings": {"type": "array", "items": {"type": "string"}},
            "main_cta": {"type": "string"},
            "listed_players": {"type": "array", "items": {"type": "string"}},
            "direct_competitor": {"type": "boolean"},
            "evidence_snippet": {"type": "string"},
            "full_transcript_summary": {"type": "string"},
            "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["category_facts", "target_facts", "players", "competitors"],
        "properties": {
            "category_facts": {"type": "array", "items": fact},
            "target_facts": {"type": "array", "items": fact},
            "players": {"type": "array", "items": player},
            "competitors": {"type": "array", "items": competitor},
        },
    }
