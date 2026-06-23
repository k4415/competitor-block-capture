from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


CONFIDENCE_VALUES = {"High", "Medium", "Low"}


@dataclass(frozen=True)
class SourceDocument:
    url: str
    title: str
    text: str


@dataclass(frozen=True)
class ResearchFact:
    table: str
    fact: str
    category: str
    source_url: str
    source_title: str
    evidence_snippet: str
    confidence: str
    research_run_id: str
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def safe_snippet(self, max_length: int = 180) -> str:
        text = " ".join(self.evidence_snippet.split())
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip() + "…"

    def is_usable(self) -> bool:
        return bool(self.fact.strip() and self.category.strip() and self.source_url.strip())

    def normalized_confidence(self) -> str:
        return self.confidence if self.confidence in CONFIDENCE_VALUES else "Low"


@dataclass(frozen=True)
class PlayerRecord:
    player_name: str
    source_url: str
    source_title: str
    evidence_snippet: str
    research_run_id: str
    price: str = ""
    plan: str = ""
    members: str = ""
    results: str = ""
    offer: str = ""
    official_url: str = ""
    features: list[str] = field(default_factory=list)
    confidence: str = "Medium"
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class CompetitorSiteRecord:
    url: str
    domain: str
    source_title: str
    structure_type: str
    rankings: list[str]
    main_cta: str
    listed_players: list[str]
    direct_competitor: bool
    evidence_snippet: str
    research_run_id: str
    full_transcript_summary: str = ""
    confidence: str = "Medium"
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class ResearchBundle:
    category_facts: list[ResearchFact]
    target_facts: list[ResearchFact]
    players: list[PlayerRecord]
    competitors: list[CompetitorSiteRecord]

    def counts(self) -> dict[str, int]:
        return {
            "category_facts": len(self.category_facts),
            "target_facts": len(self.target_facts),
            "players": len(self.players),
            "competitors": len(self.competitors),
        }
