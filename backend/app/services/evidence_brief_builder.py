"""
Build canonical evidence briefs from source, graph, search, simulation, and deliberation inputs.
"""

import re
from typing import List, Optional

from ..models.project import Project, ProjectManager
from .report_artifacts import (
    EvidenceBriefArtifact,
    SearchExecutionArtifact,
    SourceDocumentArtifact,
)
from .source_quality_ranker import SourceQualityRanker


class EvidenceBriefBuilder:
    def __init__(self):
        self.source_quality_ranker = SourceQualityRanker()

    def build(
        self,
        project: Optional[Project],
        requirement: str,
        graph_context: Optional[dict] = None,
        search_results: Optional[List[SearchExecutionArtifact]] = None,
        simulation_outputs: Optional[List[str]] = None,
        deliberation_outputs: Optional[List[str]] = None,
    ) -> EvidenceBriefArtifact:
        graph_context = graph_context or {}
        search_results = search_results or []
        simulation_outputs = simulation_outputs or []
        deliberation_outputs = deliberation_outputs or []

        extracted_text = ""
        documents: List[SourceDocumentArtifact] = []
        if project:
            extracted_text = ProjectManager.get_extracted_text(project.project_id) or ""
            for file_info in project.files:
                documents.append(
                    SourceDocumentArtifact(
                        title=file_info.get("original_filename") or file_info.get("filename") or "Source document",
                        path=file_info.get("path", ""),
                        size=int(file_info.get("size", 0) or 0),
                        summary=self._summarize_document(extracted_text),
                    )
                )

        graph_facts = [
            self._stringify_fact(item)
            for item in graph_context.get("related_facts", [])[:12]
        ]
        graph_stats = graph_context.get("graph_statistics", {})
        if graph_stats:
            graph_facts.append(
                "Graph statistics: "
                f"{graph_stats.get('total_nodes', 0)} nodes, "
                f"{graph_stats.get('total_edges', 0)} edges."
            )

        combined_text = "\n".join(
            [requirement, extracted_text, *graph_facts, *simulation_outputs, *deliberation_outputs]
            + [result.answer for result in search_results]
        )

        contradictions = self._detect_contradictions(combined_text)

        freshness_notes = []
        for result in search_results:
            freshness_notes.append(f"{result.query}: {result.freshness}")

        provenance_notes = [
            "Uploaded documents are treated as the primary anchor.",
            "External search fills recency gaps, verification needs, and counterevidence.",
            "Graph retrieval contributes structured context, not standalone truth.",
        ]
        if simulation_outputs:
            provenance_notes.append("Simulation outputs are used as exploratory stress-test evidence.")
        if deliberation_outputs:
            provenance_notes.append("Deliberation outputs are used as structured objections and counterarguments.")

        return EvidenceBriefArtifact(
            source_documents=documents,
            key_entities=self._extract_entities(combined_text),
            key_claims=self._extract_claims(combined_text),
            key_numbers=self._extract_numbers(combined_text),
            timeline_signals=self._extract_timeline_signals(combined_text),
            major_unknowns=self._extract_unknowns(combined_text),
            contradictions=contradictions,
            external_evidence=search_results,
            graph_facts=graph_facts,
            simulation_outputs=simulation_outputs[:12],
            deliberation_outputs=deliberation_outputs[:12],
            provenance_notes=provenance_notes,
            freshness_notes=freshness_notes,
        )

    def _summarize_document(self, text: str) -> str:
        excerpt = " ".join(text.split())
        return excerpt[:240] + ("..." if len(excerpt) > 240 else "")

    def _extract_entities(self, text: str) -> List[str]:
        candidates = re.findall(r"\b[A-Z][a-zA-Z0-9&-]{2,}\b", text)
        deduped = []
        seen = set()
        for item in candidates:
            if item.lower() in seen:
                continue
            seen.add(item.lower())
            deduped.append(item)
        return deduped[:20]

    def _extract_claims(self, text: str) -> List[str]:
        claims = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            sentence = sentence.strip()
            if len(sentence) < 40:
                continue
            lower = sentence.lower()
            if any(
                token in lower
                for token in [
                    " is ",
                    " are ",
                    " will ",
                    " could ",
                    " should ",
                    " due to ",
                    " because ",
                    " increase",
                    " decrease",
                ]
            ):
                claims.append(sentence)
        return claims[:24]

    def _extract_numbers(self, text: str) -> List[str]:
        numbers = re.findall(r"(?:[$€£]?\d[\d,]*(?:\.\d+)?%?(?:\s?(?:million|billion|thousand|k|m|b))?)", text, re.IGNORECASE)
        deduped = []
        seen = set()
        for item in numbers:
            normalized = item.lower().strip()
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(item.strip())
        return deduped[:20]

    def _extract_timeline_signals(self, text: str) -> List[str]:
        signals = re.findall(
            r"\b(?:by|within|during|after|before|in)\s+(?:q[1-4]\s+)?(?:\d+\s+\w+|20\d{2}|next quarter|next year|this year)\b",
            text,
            re.IGNORECASE,
        )
        return list(dict.fromkeys(signal.strip() for signal in signals))[:12]

    def _extract_unknowns(self, text: str) -> List[str]:
        unknowns = []
        lower = text.lower()
        if "market size" not in lower:
            unknowns.append("Market size or baseline demand remains unclear.")
        if "benchmark" not in lower:
            unknowns.append("Benchmark context is thin or absent.")
        if "regulation" in lower and "scope" not in lower:
            unknowns.append("Regulatory scope and enforcement specifics remain unclear.")
        if not re.search(r"\b20\d{2}\b", text):
            unknowns.append("Source recency is not consistently stated.")
        return unknowns[:8]

    def _detect_contradictions(self, text: str) -> List[str]:
        contradictions = []
        lower = text.lower()
        if "increase" in lower and "decrease" in lower:
            contradictions.append("The evidence includes both increase and decrease directional claims that need reconciliation.")
        if "high confidence" in lower and "uncertain" in lower:
            contradictions.append("Confidence language is mixed between high confidence and uncertainty.")
        return contradictions

    def _stringify_fact(self, fact: object) -> str:
        if isinstance(fact, dict):
            fact_text = fact.get("fact") or fact.get("content") or fact.get("text") or str(fact)
            return str(fact_text)
        return str(fact)
