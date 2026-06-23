from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from dataclasses import replace

from research_os.models import SourceDocument
from .agents import CategoryResearchAgent, CompetitorSiteResearchAgent, PlayerResearchAgent, TargetResearchAgent
from .browser_capture import fetch_rendered_competitor_documents
from .models import ResearchV2Bundle
from .openai_research import OpenAIResearchV2Client
from .profiles import resolve_genre_profile
from .seeds import seed_documents_for_category


@dataclass(frozen=True)
class ResearchV2Request:
    category_name: str
    competitor_urls: list[str]
    parent_page_id: str
    memo: str = ""
    depth: str = "standard"
    use_openai: bool = True
    research_run_id: str = field(default_factory=lambda: f"run-v2-{uuid.uuid4()}")


def collect_v2_research_bundle(
    request: ResearchV2Request,
    *,
    source_documents: list[SourceDocument] | None = None,
    openai_client: OpenAIResearchV2Client | None = None,
) -> ResearchV2Bundle:
    profile = resolve_genre_profile(request.category_name)
    research_request = request
    if profile.canonical_name != request.category_name:
        research_request = replace(request, category_name=profile.canonical_name)
    docs: list[SourceDocument] = []
    seed_docs: list[SourceDocument] = []
    competitor_docs: list[SourceDocument] = []
    client = openai_client or OpenAIResearchV2Client()
    if source_documents is not None:
        docs.extend(source_documents)
        research_mode = "provided_sources"
    else:
        seed_docs = seed_documents_for_category(research_request.category_name)
        competitor_docs = fetch_rendered_competitor_documents(request.competitor_urls)
        docs.extend(seed_docs)
        docs.extend(competitor_docs)
        research_mode = "openai" if request.use_openai and client.available() else "local_fallback"
    diagnostics = {
        "openai_available": client.available(),
        "seed_source_count": len(seed_docs),
        "competitor_source_count": len(competitor_docs),
        "research_mode": research_mode,
    }

    if request.use_openai and client.available():
        return _with_diagnostics(client.research(research_request, source_documents=docs), diagnostics)

    failed_urls = [doc.url for doc in docs if "取得失敗" in doc.text]
    category_agent = CategoryResearchAgent()
    target_agent = TargetResearchAgent()
    player_agent = PlayerResearchAgent()
    competitor_agent = CompetitorSiteResearchAgent()
    bundle = ResearchV2Bundle(
        category_facts=category_agent.extract(docs, category_name=research_request.category_name, research_run_id=request.research_run_id),
        target_facts=target_agent.extract(docs, category_name=research_request.category_name, research_run_id=request.research_run_id),
        players=player_agent.extract(docs, research_run_id=request.research_run_id, category_name=research_request.category_name),
        competitors=competitor_agent.extract(
            docs,
            competitor_urls=request.competitor_urls,
            research_run_id=request.research_run_id,
            category_name=research_request.category_name,
        ),
        source_count=len(docs),
        failed_urls=failed_urls,
        diagnostics=diagnostics,
    )
    return bundle


def _with_diagnostics(bundle: ResearchV2Bundle, diagnostics: dict[str, object]) -> ResearchV2Bundle:
    return replace(bundle, diagnostics=diagnostics)
