"""
Unified web search, enrichment, and fact-checking service
Uses the multi-provider LLM abstraction for web search capabilities
"""

import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_provider import (
    LLMProvider, ProviderFactory, WebSearchResult, Citation
)

logger = get_logger('mirofish.search_service')


@dataclass
class EnrichmentResult:
    """Result from document enrichment"""
    original_requirement: str
    queries_used: List[str] = field(default_factory=list)
    supplementary_context: str = ""
    citations: List[Citation] = field(default_factory=list)
    total_sources: int = 0


@dataclass
class FactCheckResult:
    """Result from fact checking"""
    claim: str
    verdict: str  # "supported", "contradicted", "inconclusive"
    confidence: float = 0.0
    supporting_sources: List[Citation] = field(default_factory=list)
    contradicting_sources: List[Citation] = field(default_factory=list)
    explanation: str = ""


class SearchService:
    """
    Unified search service providing web search, document enrichment, and fact-checking.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self._provider = provider
        self._search_log: List[Dict[str, Any]] = []
        logger.info("SearchService initialized")

    @property
    def provider(self) -> LLMProvider:
        """Lazily create search provider"""
        if self._provider is None:
            self._provider = ProviderFactory.create_search_provider()
        return self._provider

    def search(self, query: str, context: str = "") -> WebSearchResult:
        """
        Perform a web search.

        Args:
            query: Search query
            context: Optional context for the search

        Returns:
            WebSearchResult with answer and citations
        """
        logger.info(f"Web search: {query[:80]}...")
        result = self.provider.web_search(query=query, context=context)

        # Log the search
        self._search_log.append({
            "query": query,
            "citations_count": len(result.citations),
            "answer_length": len(result.answer)
        })

        logger.info(f"Search complete: {len(result.citations)} citations")
        return result

    def search_batch(self, queries: List[str]) -> List[WebSearchResult]:
        """
        Perform multiple searches.

        Args:
            queries: List of search queries

        Returns:
            List of WebSearchResult
        """
        results = []
        for query in queries:
            result = self.search(query)
            results.append(result)
        return results

    def enrich_document(self, document_text: str, requirement: str) -> EnrichmentResult:
        """
        Enrich a document with web search context.
        Auto-generates 3-5 search queries from the document, searches, and returns supplementary context.

        Args:
            document_text: The document text to enrich
            requirement: The simulation/research requirement

        Returns:
            EnrichmentResult with supplementary context and citations
        """
        logger.info("Enriching document with web search...")

        # Generate search queries from the document
        query_gen_prompt = f"""Based on this research requirement and document excerpt, generate 3-5 search queries
that would find relevant background information, recent news, or expert analysis.

Research requirement: {requirement}

Document excerpt (first 2000 chars):
{document_text[:2000]}

Return a JSON object: {{"queries": ["query1", "query2", ...]}}"""

        try:
            response = self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a research assistant. Generate web search queries to find relevant context. Return valid JSON."},
                    {"role": "user", "content": query_gen_prompt}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            import re
            content = response.content.strip()
            content = re.sub(r'^```(?:json)?\s*\n?', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\n?```\s*$', '', content)
            queries_data = json.loads(content.strip())
            queries = queries_data.get("queries", [])[:5]

        except Exception as e:
            logger.warning(f"Failed to generate search queries: {e}")
            queries = [requirement]

        # Search for each query
        all_citations = []
        context_parts = []

        for query in queries:
            result = self.search(query, context=f"Research context: {requirement}")
            if result.answer:
                context_parts.append(f"### {query}\n{result.answer}")
            all_citations.extend(result.citations)

        enrichment = EnrichmentResult(
            original_requirement=requirement,
            queries_used=queries,
            supplementary_context="\n\n".join(context_parts),
            citations=all_citations,
            total_sources=len(all_citations)
        )

        logger.info(f"Enrichment complete: {len(queries)} queries, {len(all_citations)} citations")
        return enrichment

    def fact_check(self, claim: str) -> FactCheckResult:
        """
        Fact-check a claim by searching for evidence.

        Args:
            claim: The claim to fact-check

        Returns:
            FactCheckResult with verdict and sources
        """
        logger.info(f"Fact-checking: {claim[:80]}...")

        # Search for evidence
        search_result = self.search(
            query=f"Is it true that {claim}",
            context="You are a fact-checker. Find evidence supporting or contradicting this claim. Be objective."
        )

        # Analyze the evidence
        analysis_prompt = f"""Based on the following search results, fact-check this claim:

Claim: {claim}

Search results:
{search_result.answer}

Provide your analysis as JSON:
{{
    "verdict": "supported" or "contradicted" or "inconclusive",
    "confidence": 0.0 to 1.0,
    "explanation": "brief explanation"
}}"""

        try:
            response = self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are an objective fact-checker. Analyze evidence and provide verdicts. Return valid JSON."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            import re
            content = response.content.strip()
            content = re.sub(r'^```(?:json)?\s*\n?', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\n?```\s*$', '', content)
            analysis = json.loads(content.strip())

            verdict = analysis.get("verdict", "inconclusive")
            confidence = float(analysis.get("confidence", 0.5))
            explanation = analysis.get("explanation", "")

        except Exception as e:
            logger.warning(f"Fact-check analysis failed: {e}")
            verdict = "inconclusive"
            confidence = 0.0
            explanation = f"Analysis failed: {str(e)}"

        # Categorize citations
        supporting = []
        contradicting = []
        for cite in search_result.citations:
            if verdict == "supported":
                supporting.append(cite)
            elif verdict == "contradicted":
                contradicting.append(cite)

        return FactCheckResult(
            claim=claim,
            verdict=verdict,
            confidence=confidence,
            supporting_sources=supporting,
            contradicting_sources=contradicting,
            explanation=explanation
        )

    def get_search_log(self) -> List[Dict[str, Any]]:
        """Get the search history log"""
        return self._search_log.copy()
