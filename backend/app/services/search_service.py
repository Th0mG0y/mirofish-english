"""
Unified web search, enrichment, and fact-checking service
Uses the multi-provider LLM abstraction for web search capabilities
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_provider import LLMProvider, ProviderFactory, WebSearchResult, Citation
from .report_artifacts import SearchExecutionArtifact
from .source_quality_ranker import SourceQualityRanker

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


@dataclass
class SearchLogEntry:
    query: str
    intent: str = "discovery"
    context: str = ""
    report_question: str = ""
    evidence_type: str = ""
    citations_count: int = 0
    answer_length: int = 0
    usable_evidence: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "context": self.context,
            "report_question": self.report_question,
            "evidence_type": self.evidence_type,
            "citations_count": self.citations_count,
            "answer_length": self.answer_length,
            "usable_evidence": self.usable_evidence,
            "timestamp": self.timestamp,
        }


class SearchService:
    """
    Unified search service providing web search, document enrichment, and fact-checking.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self._provider = provider
        self._search_log: List[SearchLogEntry] = []
        self._ranker = SourceQualityRanker()
        logger.info("SearchService initialized")

    @property
    def provider(self) -> LLMProvider:
        """Lazily create search provider"""
        if self._provider is None:
            self._provider = ProviderFactory.create_search_provider()
        return self._provider

    def search(
        self,
        query: str,
        context: str = "",
        intent: str = "discovery",
        report_question: str = "",
        evidence_type: str = "",
    ) -> WebSearchResult:
        """
        Perform a web search.

        Args:
            query: Search query
            context: Optional context for the search

        Returns:
            WebSearchResult with answer and citations
        """
        logger.info(f"Web search: {query[:80]}...")
        if not self.provider.supports_web_search():
            message = (
                "The configured search provider does not support built-in web search. "
                "Use Anthropic or the real OpenAI API for search."
            )
            logger.warning(message)
            result = WebSearchResult(query=query, answer=message, citations=[])
            self._append_search_log(
                query=query,
                context=context,
                intent=intent,
                report_question=report_question,
                evidence_type=evidence_type,
                result=result,
            )
            return result

        result = self.provider.web_search(query=query, context=context)

        self._append_search_log(
            query=query,
            context=context,
            intent=intent,
            report_question=report_question,
            evidence_type=evidence_type,
            result=result,
        )

        logger.info(f"Search complete: {len(result.citations)} citations")
        return result

    def _append_search_log(
        self,
        query: str,
        context: str,
        intent: str,
        report_question: str,
        evidence_type: str,
        result: WebSearchResult,
    ) -> None:
        self._search_log.append(
            SearchLogEntry(
                query=query,
                intent=intent,
                context=context,
                report_question=report_question,
                evidence_type=evidence_type,
                citations_count=len(result.citations),
                answer_length=len(result.answer or ""),
                usable_evidence=bool((result.answer or "").strip()) or bool(result.citations),
            )
        )

    def _dedupe_citations(self, citations: List[Citation]) -> List[Citation]:
        seen = set()
        deduped = []
        for citation in citations:
            key = (
                (citation.url or "").strip().lower(),
                (citation.title or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(citation)
        return deduped

    def _format_search_context(self, query: str, result: WebSearchResult) -> str:
        parts = [f"### {query}", ""]

        if result.answer:
            parts.append(result.answer)
        else:
            parts.append("No answer summary returned.")

        if result.citations:
            parts.extend(["", "**Sources**"])
            for citation in result.citations:
                title = citation.title or citation.url or "Untitled source"
                snippet = citation.snippet or "No snippet available."
                parts.append(f"- [{title}]({citation.url}): {snippet}")

        return "\n".join(parts)

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

    def search_plan(self, queries: List[Dict[str, Any]]) -> List[SearchExecutionArtifact]:
        executions: List[SearchExecutionArtifact] = []
        for query_spec in queries:
            context_parts = []
            if query_spec.get("source_chunk"):
                context_parts.append(query_spec.get("source_chunk"))
            elif query_spec.get("reason"):
                context_parts.append(query_spec.get("reason"))
            result = self.search(
                query=query_spec.get("query", ""),
                context="\n\n".join(part for part in context_parts if part),
                intent=query_spec.get("intent", "discovery"),
                report_question=query_spec.get("report_question", ""),
                evidence_type=query_spec.get("evidence_type", ""),
            )
            quality_summary = self._ranker.summarize(result.citations, query_spec.get("query", ""))
            ranked_sources = self._ranker.rank_sources(result.citations, query_spec.get("query", ""))
            relevant_sources = [
                item for item in ranked_sources
                if item.relevance != "off_topic" and item.score >= 0.35
            ]
            freshness = quality_summary.get("freshness", "unknown")
            executions.append(
                SearchExecutionArtifact(
                    query=query_spec.get("query", ""),
                    intent=query_spec.get("intent", "discovery"),
                    answer=result.answer if relevant_sources else "",
                    citations=[self._citation_to_dict(item.citation) for item in relevant_sources[:5]],
                    usable_evidence=bool(relevant_sources),
                    source_quality_summary=quality_summary,
                    freshness=freshness,
                )
            )
        return executions

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
            result = self.search(
                query,
                context=f"Research context: {requirement}",
                intent="discovery",
                report_question=requirement,
                evidence_type="supplementary_context",
            )
            context_parts.append(self._format_search_context(query, result))
            all_citations.extend(result.citations)

        deduped_citations = self._dedupe_citations(all_citations)

        enrichment = EnrichmentResult(
            original_requirement=requirement,
            queries_used=queries,
            supplementary_context="\n\n".join(context_parts),
            citations=deduped_citations,
            total_sources=len(deduped_citations)
        )

        logger.info(f"Enrichment complete: {len(queries)} queries, {len(deduped_citations)} citations")
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
            context="You are a fact-checker. Find evidence supporting or contradicting this claim. Be objective.",
            intent="verification",
            report_question=claim,
            evidence_type="claim_verification",
        )
        ranked_sources = self._ranker.rank_sources(search_result.citations, claim)
        relevant_sources = [
            item for item in ranked_sources
            if item.relevance != "off_topic" and item.score >= 0.4
        ]

        if not relevant_sources:
            return FactCheckResult(
                claim=claim,
                verdict="inconclusive",
                confidence=0.0,
                explanation="Search did not return directly relevant sources for this claim.",
            )

        evidence_text = search_result.answer.strip()
        if relevant_sources:
            evidence_lines = []
            for item in relevant_sources[:5]:
                title = item.citation.title or item.citation.url or "Untitled source"
                snippet = item.citation.snippet or "No snippet available."
                evidence_lines.append(
                    f"- [{item.source_type} | {item.relevance} | score={item.score:.2f}] {title}: {snippet}"
                )
            evidence_text = "\n".join([evidence_text, "", "Relevant citations:", *evidence_lines]).strip()

        # Analyze the evidence
        analysis_prompt = f"""Based on the following search results, fact-check this claim:

Claim: {claim}

Search results:
{evidence_text}

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

        has_strong_direct_evidence = any(
            item.relevance == "direct" and item.score >= 0.5
            for item in relevant_sources
        )
        if verdict in {"supported", "contradicted"} and not has_strong_direct_evidence:
            verdict = "inconclusive"
            confidence = min(confidence, 0.35)
            explanation = "Search returned only weakly relevant sources, so the claim remains unresolved."

        # Categorize citations
        supporting = []
        contradicting = []
        for item in relevant_sources:
            cite = item.citation
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
        return [entry.to_dict() for entry in self._search_log]

    def _citation_to_dict(self, citation: Citation) -> Dict[str, str]:
        return {
            "url": citation.url,
            "title": citation.title,
            "snippet": citation.snippet,
        }
