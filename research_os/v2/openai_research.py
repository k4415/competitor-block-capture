from __future__ import annotations

import json
import os
from typing import Any
from urllib import request as urlrequest

from research_os.models import SourceDocument

from .models import CompetitorSiteV2Record, PlayerV2Record, ResearchV2Bundle, ResearchV2Fact
from .profiles import resolve_genre_profile


RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
PLAYER_SECTIONS = ["特徴", "メリット", "実績", "権威性", "オファー", "リスク・制約", "会社情報"]


class OpenAIResearchV2Client:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 180) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    def research(self, request: object, source_documents: list[SourceDocument] | None = None) -> ResearchV2Bundle:
        docs = source_documents or []
        category_facts = self.research_category(request, docs)
        target_facts = self.research_target(request, docs)
        players = self.research_players(request, docs)
        competitors = self.research_competitors(request, docs)
        return ResearchV2Bundle(
            category_facts=category_facts,
            target_facts=target_facts,
            players=players,
            competitors=competitors,
            source_count=len(docs),
            failed_urls=[doc.url for doc in docs if "取得失敗" in doc.text],
        )

    def research_category(self, request: object, docs: list[SourceDocument]) -> list[ResearchV2Fact]:
        profile = resolve_genre_profile(getattr(request, "category_name"))
        payload = self._post_json(
            "category_research",
            _facts_schema("category_facts"),
            _prompt(
                request,
                docs,
                f"カテゴリーリサーチ。大項目はprofileのカテゴリーリサーチ項目から選ぶ。必須項目: {' / '.join(profile.category_topics)}。",
            ),
        )
        return [_fact(item, getattr(request, "research_run_id")) for item in payload.get("category_facts", [])]

    def research_target(self, request: object, docs: list[SourceDocument]) -> list[ResearchV2Fact]:
        profile = resolve_genre_profile(getattr(request, "category_name"))
        payload = self._post_json(
            "target_research",
            _facts_schema("target_facts"),
            _prompt(
                request,
                docs,
                f"ターゲットリサーチ。セグメントはprofileのターゲットセグメントを優先し、大項目は デモグラ / 利用前状態 / 欲求 / 懸念 / ビリーフ / 比較対象 / 購入/申込トリガー / 意思決定基準 / 予算感 / 不安解消条件 から選ぶ。優先セグメント: {' / '.join(profile.target_segments)}。",
            ),
        )
        return [_fact(item, getattr(request, "research_run_id")) for item in payload.get("target_facts", [])]

    def research_players(self, request: object, docs: list[SourceDocument]) -> list[PlayerV2Record]:
        payload = self._post_json(
            "player_research",
            _players_schema(),
            _prompt(
                request,
                docs,
                "メインプレイヤーリサーチ。公式URL由来を優先し、各サービスを 特徴 / メリット / 実績 / 権威性 / オファー / リスク・制約 / 会社情報 の7章で埋める。",
            ),
        )
        return [_player(item, getattr(request, "research_run_id")) for item in payload.get("players", [])]

    def research_competitors(self, request: object, docs: list[SourceDocument]) -> list[CompetitorSiteV2Record]:
        payload = self._post_json(
            "competitor_research",
            _competitors_schema(),
            _prompt(
                request,
                docs,
                "競合比較サイトリサーチ。全文転載せず、構成順 / 見出し / ランキング1-5 / CTA / 掲載サービス / 画像内主要文言 / 比較軸 / 証拠表現 / 訴求パターンを構造化する。",
            ),
        )
        return [_competitor(item, getattr(request, "research_run_id")) for item in payload.get("competitors", [])]

    def _post_json(self, schema_name: str, schema: dict[str, Any], prompt: str) -> dict[str, Any]:
        req = urlrequest.Request(
            RESPONSES_ENDPOINT,
            data=json.dumps(
                {
                    "model": self.model,
                    "input": prompt,
                    "tools": [{"type": os.getenv("OPENAI_WEB_SEARCH_TOOL", "web_search_preview")}],
                    "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=self.timeout) as response:
            return _extract_json(json.loads(response.read().decode("utf-8")))


def _prompt(request: object, docs: list[SourceDocument], instruction: str) -> str:
    profile = resolve_genre_profile(getattr(request, "category_name"))
    excerpts = "\n\n".join(f"URL: {doc.url}\nTITLE: {doc.title}\nTEXT: {_truncate(doc.text, 2500)}" for doc in docs[:16])
    return (
        "日本語で比較リスティング広告用のリサーチを実行してください。"
        "1 fact = 1 row。根拠URLがない事実は出力しない。短い引用は180字以内。"
        "第三者サイト本文の丸ごと転載は禁止。"
        f"\nカテゴリ: {getattr(request, 'category_name')}"
        f"\n正規カテゴリ: {profile.canonical_name}"
        f"\nカテゴリ種別: {profile.category_type}"
        f"\nカテゴリーリサーチ項目: {' / '.join(profile.category_topics)}"
        f"\nターゲットセグメント: {' / '.join(profile.target_segments)}"
        f"\nメインプレイヤー発見語: {' / '.join(profile.player_discovery_terms)}"
        f"\n検索深度: {getattr(request, 'depth')}"
        f"\nメモ: {getattr(request, 'memo')}"
        f"\n指示: {instruction}"
        f"\n入力ソース:\n{excerpts}"
    )


def _extract_json(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("output_text"):
        return json.loads(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return json.loads(text)
    raise RuntimeError("OpenAI response did not contain JSON text")


def _fact(item: dict[str, Any], research_run_id: str) -> ResearchV2Fact:
    return ResearchV2Fact(
        fact=item.get("fact", ""),
        major_category=item.get("major_category", ""),
        sub_category=item.get("sub_category", ""),
        segment=item.get("segment", "共通"),
        source_url=item.get("source_url", ""),
        source_title=item.get("source_title", ""),
        evidence_snippet=item.get("evidence_snippet", ""),
        confidence=item.get("confidence", "中"),
        verification_status=item.get("verification_status", "要確認"),
        research_run_id=research_run_id,
    )


def _player(item: dict[str, Any], research_run_id: str) -> PlayerV2Record:
    sections = {name: item.get("sections", {}).get(name, []) for name in PLAYER_SECTIONS}
    return PlayerV2Record(
        player_name=item.get("player_name", ""),
        official_url=item.get("official_url", ""),
        source_url=item.get("source_url", ""),
        source_title=item.get("source_title", ""),
        evidence_snippet=item.get("evidence_snippet", ""),
        confidence=item.get("confidence", "中"),
        verification_status=item.get("verification_status", "要確認"),
        research_run_id=research_run_id,
        sections=sections,
        price=item.get("price", ""),
        plan=item.get("plan", ""),
        members=item.get("members", ""),
        results=item.get("results", ""),
        offer=item.get("offer", ""),
    )


def _competitor(item: dict[str, Any], research_run_id: str) -> CompetitorSiteV2Record:
    return CompetitorSiteV2Record(
        url=item.get("url", ""),
        domain=item.get("domain", ""),
        source_title=item.get("source_title", ""),
        evidence_snippet=item.get("evidence_snippet", ""),
        confidence=item.get("confidence", "中"),
        verification_status=item.get("verification_status", "要確認"),
        research_run_id=research_run_id,
        structure_type=item.get("structure_type", "不明"),
        rankings=item.get("rankings", []),
        main_cta=item.get("main_cta", ""),
        listed_players=item.get("listed_players", []),
        image_text_summary=item.get("image_text_summary", ""),
        structured_body=item.get("structured_body", ""),
        direct_competitor=bool(item.get("direct_competitor", False)),
    )


def _facts_schema(key: str) -> dict[str, Any]:
    fact = {
        "type": "object",
        "additionalProperties": False,
        "required": ["fact", "major_category", "sub_category", "segment", "source_url", "source_title", "evidence_snippet", "confidence", "verification_status"],
        "properties": _fact_properties(),
    }
    return {"type": "object", "additionalProperties": False, "required": [key], "properties": {key: {"type": "array", "items": fact}}}


def _players_schema() -> dict[str, Any]:
    section_props = {name: {"type": "array", "items": {"type": "string"}} for name in PLAYER_SECTIONS}
    player = {
        "type": "object",
        "additionalProperties": False,
        "required": ["player_name", "official_url", "source_url", "source_title", "evidence_snippet", "confidence", "verification_status", "sections", "price", "plan", "members", "results", "offer"],
        "properties": {
            "player_name": {"type": "string"},
            "official_url": {"type": "string"},
            "source_url": {"type": "string"},
            "source_title": {"type": "string"},
            "evidence_snippet": {"type": "string"},
            "confidence": {"type": "string", "enum": ["高", "中", "低"]},
            "verification_status": {"type": "string", "enum": ["検証済み", "要確認", "取得失敗"]},
            "sections": {"type": "object", "additionalProperties": False, "required": PLAYER_SECTIONS, "properties": section_props},
            "price": {"type": "string"},
            "plan": {"type": "string"},
            "members": {"type": "string"},
            "results": {"type": "string"},
            "offer": {"type": "string"},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": ["players"], "properties": {"players": {"type": "array", "items": player}}}


def _competitors_schema() -> dict[str, Any]:
    competitor = {
        "type": "object",
        "additionalProperties": False,
        "required": ["url", "domain", "source_title", "evidence_snippet", "confidence", "verification_status", "structure_type", "rankings", "main_cta", "listed_players", "image_text_summary", "structured_body", "direct_competitor"],
        "properties": {
            "url": {"type": "string"},
            "domain": {"type": "string"},
            "source_title": {"type": "string"},
            "evidence_snippet": {"type": "string"},
            "confidence": {"type": "string", "enum": ["高", "中", "低"]},
            "verification_status": {"type": "string", "enum": ["検証済み", "要確認", "取得失敗"]},
            "structure_type": {"type": "string"},
            "rankings": {"type": "array", "items": {"type": "string"}},
            "main_cta": {"type": "string"},
            "listed_players": {"type": "array", "items": {"type": "string"}},
            "image_text_summary": {"type": "string"},
            "structured_body": {"type": "string"},
            "direct_competitor": {"type": "boolean"},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": ["competitors"], "properties": {"competitors": {"type": "array", "items": competitor}}}


def _fact_properties() -> dict[str, Any]:
    return {
        "fact": {"type": "string"},
        "major_category": {"type": "string"},
        "sub_category": {"type": "string"},
        "segment": {"type": "string"},
        "source_url": {"type": "string"},
        "source_title": {"type": "string"},
        "evidence_snippet": {"type": "string"},
        "confidence": {"type": "string", "enum": ["高", "中", "低"]},
        "verification_status": {"type": "string", "enum": ["検証済み", "要確認", "取得失敗"]},
    }


def _truncate(text: str, max_length: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"
