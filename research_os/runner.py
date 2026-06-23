from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .extractors import HeuristicExtractor
from .models import ResearchBundle, SourceDocument
from .openai_research import OpenAIResearchClient
from .sources import fetch_many


@dataclass(frozen=True)
class ResearchRequest:
    category_name: str
    competitor_urls: list[str]
    parent_page_id: str
    memo: str = ""
    depth: str = "standard"
    use_openai: bool = True
    research_run_id: str = field(default_factory=lambda: f"run-{uuid.uuid4()}")


def collect_research_bundle(
    request: ResearchRequest,
    *,
    source_documents: list[SourceDocument] | None = None,
    openai_client: OpenAIResearchClient | None = None,
) -> ResearchBundle:
    client = openai_client or OpenAIResearchClient()
    if request.use_openai and client.available():
        return client.research(
            category_name=request.category_name,
            memo=request.memo,
            competitor_urls=request.competitor_urls,
            depth=request.depth,
            research_run_id=request.research_run_id,
        )

    docs = source_documents if source_documents is not None else fetch_many(request.competitor_urls)
    extractor = HeuristicExtractor()
    return ResearchBundle(
        category_facts=extractor.extract_category_facts(docs, category_name=request.category_name, research_run_id=request.research_run_id),
        target_facts=extractor.extract_target_facts(docs, category_name=request.category_name, research_run_id=request.research_run_id),
        players=extractor.extract_players(docs, research_run_id=request.research_run_id),
        competitors=[extractor.extract_competitor_site(doc, research_run_id=request.research_run_id, direct=doc.url in request.competitor_urls) for doc in docs],
    )
