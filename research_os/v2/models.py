from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


CONFIDENCE_VALUES = {"高", "中", "低"}
VERIFICATION_VALUES = {"検証済み", "要確認", "取得失敗"}


@dataclass(frozen=True)
class ResearchV2Fact:
    fact: str
    major_category: str
    sub_category: str
    segment: str
    source_url: str
    source_title: str
    evidence_snippet: str
    confidence: str
    verification_status: str
    research_run_id: str
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_usable(self) -> bool:
        return bool(self.fact.strip() and self.major_category.strip() and self.source_url.strip())

    def safe_snippet(self, max_length: int = 180) -> str:
        text = " ".join(self.evidence_snippet.split())
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip() + "…"

    def normalized_confidence(self) -> str:
        return self.confidence if self.confidence in CONFIDENCE_VALUES else "低"

    def normalized_verification_status(self) -> str:
        return self.verification_status if self.verification_status in VERIFICATION_VALUES else "要確認"


@dataclass(frozen=True)
class PlayerV2Record:
    player_name: str
    official_url: str
    source_url: str
    source_title: str
    evidence_snippet: str
    confidence: str
    verification_status: str
    research_run_id: str
    sections: dict[str, list[str]]
    price: str = ""
    plan: str = ""
    members: str = ""
    results: str = ""
    offer: str = ""
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def normalized_confidence(self) -> str:
        return self.confidence if self.confidence in CONFIDENCE_VALUES else "低"

    def normalized_verification_status(self) -> str:
        return self.verification_status if self.verification_status in VERIFICATION_VALUES else "要確認"


@dataclass(frozen=True)
class CompetitorSiteV2Record:
    url: str
    domain: str
    source_title: str
    evidence_snippet: str
    confidence: str
    verification_status: str
    research_run_id: str
    structure_type: str
    rankings: list[str]
    main_cta: str
    listed_players: list[str]
    image_text_summary: str
    structured_body: str
    direct_competitor: bool
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def normalized_confidence(self) -> str:
        return self.confidence if self.confidence in CONFIDENCE_VALUES else "低"

    def normalized_verification_status(self) -> str:
        return self.verification_status if self.verification_status in VERIFICATION_VALUES else "要確認"


@dataclass(frozen=True)
class ResearchV2Bundle:
    category_facts: list[ResearchV2Fact]
    target_facts: list[ResearchV2Fact]
    players: list[PlayerV2Record]
    competitors: list[CompetitorSiteV2Record]
    source_count: int = 0
    failed_urls: list[str] = field(default_factory=list)
    diagnostics: dict[str, object] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "category_facts": len(self.category_facts),
            "target_facts": len(self.target_facts),
            "players": len(self.players),
            "competitors": len(self.competitors),
        }

    def needs_review_count(self) -> int:
        total = 0
        total += sum(1 for fact in self.category_facts + self.target_facts if fact.normalized_verification_status() != "検証済み")
        total += sum(1 for player in self.players if player.normalized_verification_status() != "検証済み")
        total += sum(1 for competitor in self.competitors if competitor.normalized_verification_status() != "検証済み")
        return total
