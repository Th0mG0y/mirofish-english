"""
Claim ledger construction and helpers.
"""

import re
import uuid
from typing import List, Optional, Sequence, Set

from .constraint_mapper import ConstraintMapper
from .report_artifacts import (
    ClaimLedgerEntry,
    EvidenceBriefArtifact,
    ReportIntentArtifact,
    RepresentativenessArtifact,
)


class ClaimLedgerBuilder:
    def __init__(self):
        self.constraint_mapper = ConstraintMapper()

    def build(
        self,
        intent: ReportIntentArtifact,
        evidence_brief: EvidenceBriefArtifact,
        schema_sections: Optional[Sequence[str]] = None,
    ) -> List[ClaimLedgerEntry]:
        claims = []
        seen = set()

        for claim_text in evidence_brief.key_claims[:18]:
            normalized = self._normalize(claim_text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            category = self._classify_claim(claim_text)
            provenance = self._detect_provenance(claim_text, evidence_brief)
            confidence = self._confidence_for(claim_text, provenance, evidence_brief)
            claims.append(
                ClaimLedgerEntry(
                    claim_id=f"claim_{uuid.uuid4().hex[:10]}",
                    claim_text=claim_text,
                    canonical_claim_text=claim_text,
                    claim_fingerprint=self._claim_fingerprint(claim_text),
                    cluster_id=f"cluster_{uuid.uuid4().hex[:8]}",
                    claim_category=category,
                    source_provenance=provenance,
                    supporting_evidence=self._supporting_evidence(claim_text, evidence_brief),
                    citation_links=self._citation_links(evidence_brief),
                    confidence=confidence,
                    dependencies=self._dependencies(claim_text),
                    contested=self._is_contested(claim_text, evidence_brief),
                    report_sections=self._default_sections(intent, category),
                    representativeness=self._representativeness(claim_text),
                    constraint_map=self.constraint_mapper.build(claim_text, intent.report_type),
                    source_freshness=self._freshness(evidence_brief),
                )
            )

        consolidated = self._consolidate_claims(claims)
        self._assign_section_ownership(consolidated, intent, schema_sections or [])
        return consolidated

    def filter_for_section(self, ledger: List[ClaimLedgerEntry], section_title: str) -> List[ClaimLedgerEntry]:
        title = section_title.lower()
        matches = [
            entry for entry in ledger
            if entry.primary_section.lower() == title
        ]
        if matches:
            return matches
        fallback = [
            entry for entry in ledger
            if any(section.lower() == title for section in entry.report_sections)
        ]
        if fallback:
            return fallback[:6]
        return ledger[:6]

    def consolidate_for_section(
        self,
        ledger: List[ClaimLedgerEntry],
        section_title: str,
        prior_sections: Sequence[str],
    ) -> List[ClaimLedgerEntry]:
        prior_claims = self._normalize(" ".join(prior_sections))
        section_claims = self.filter_for_section(ledger, section_title)
        selected = []
        seen_clusters = set()
        for entry in section_claims:
            if entry.cluster_id in seen_clusters:
                continue
            canonical = entry.canonical_claim_text or entry.claim_text
            if canonical and self._normalize(canonical) and self._normalize(canonical) in prior_claims:
                continue
            seen_clusters.add(entry.cluster_id)
            selected.append(entry)
        return selected[:6]

    def _classify_claim(self, text: str) -> str:
        lower = text.lower()
        if any(char.isdigit() for char in text):
            return "numeric"
        if any(token in lower for token in ["will", "scenario", "forecast", "project"]):
            return "inferred"
        if any(token in lower for token in ["assume", "if", "depends"]):
            return "assumption"
        return "factual"

    def _detect_provenance(self, claim_text: str, evidence_brief: EvidenceBriefArtifact) -> List[str]:
        provenance = []
        if any(self._normalize(claim_text) in self._normalize(item) for item in evidence_brief.graph_facts):
            provenance.append("graph_retrieval")
        if any(self._normalize(claim_text) in self._normalize(item) for item in evidence_brief.simulation_outputs):
            provenance.append("simulation_output")
        if evidence_brief.external_evidence:
            provenance.append("web_evidence")
        if evidence_brief.source_documents:
            provenance.append("source_document")
        if not provenance:
            provenance.append("unresolved")
        return provenance

    def _supporting_evidence(self, claim_text: str, evidence_brief: EvidenceBriefArtifact) -> List[str]:
        support = []
        claim_tokens = set(self._normalize(claim_text).split())
        for bucket in [
            evidence_brief.graph_facts,
            evidence_brief.simulation_outputs,
            evidence_brief.deliberation_outputs,
        ]:
            for item in bucket:
                item_tokens = set(self._normalize(item).split())
                if claim_tokens and len(claim_tokens & item_tokens) >= min(3, max(1, len(claim_tokens) // 3)):
                    support.append(item)
                    if len(support) >= 4:
                        return support
        for item in evidence_brief.key_numbers:
            if any(token in claim_text for token in re.findall(r"\d[\d,.%]*", item)):
                support.append(item)
        return support[:4]

    def _citation_links(self, evidence_brief: EvidenceBriefArtifact) -> List[str]:
        links = []
        for evidence in evidence_brief.external_evidence:
            for citation in evidence.citations[:2]:
                if citation.get("url"):
                    links.append(citation["url"])
        deduped = []
        seen = set()
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            deduped.append(link)
        return deduped[:4]

    def _confidence_for(self, claim_text: str, provenance: List[str], evidence_brief: EvidenceBriefArtifact) -> float:
        score = 0.35
        if "source_document" in provenance:
            score += 0.15
        if "web_evidence" in provenance:
            score += 0.2
        if "graph_retrieval" in provenance:
            score += 0.1
        if "simulation_output" in provenance and "web_evidence" not in provenance:
            score -= 0.05
        if any(char.isdigit() for char in claim_text):
            score += 0.05
        if evidence_brief.contradictions:
            score -= 0.05
        return max(0.1, min(score, 0.95))

    def _dependencies(self, claim_text: str) -> List[str]:
        lower = claim_text.lower()
        dependencies = []
        if any(token in lower for token in ["cost", "budget", "price"]):
            dependencies.append("cost assumptions")
        if any(token in lower for token in ["regulation", "policy"]):
            dependencies.append("regulatory scope")
        if any(token in lower for token in ["market", "adoption"]):
            dependencies.append("market adoption data")
        if any(token in lower for token in ["timeline", "by ", "within "]):
            dependencies.append("timeframe assumptions")
        return dependencies

    def _is_contested(self, claim_text: str, evidence_brief: EvidenceBriefArtifact) -> bool:
        normalized = self._normalize(claim_text)
        return any(normalized and normalized[:24] in self._normalize(item) for item in evidence_brief.contradictions)

    def _default_sections(self, intent: ReportIntentArtifact, category: str) -> List[str]:
        if category == "numeric":
            return ["Quantitative Checks", "What Is Verified"]
        if intent.report_type in {"forecast", "scenario_analysis"}:
            return ["Core Thesis and Confidence", "Alternative Interpretations or Scenarios"]
        return ["Core Thesis and Confidence", "What Is Verified"]

    def _representativeness(self, claim_text: str) -> RepresentativenessArtifact:
        lower = claim_text.lower()
        evidence_class = "broad_benchmark"
        if any(token in lower for token in ["campaign", "case study", "single", "example"]):
            evidence_class = "anecdotal_example"
        elif any(token in lower for token in ["company", "internal", "organization"]):
            evidence_class = "organization_specific_metric"
        elif any(token in lower for token in ["segment", "vertical", "cohort"]):
            evidence_class = "segmented_benchmark"

        return RepresentativenessArtifact(
            evidence_class=evidence_class,
            context_specificity="high" if evidence_class != "broad_benchmark" else "medium",
            causal_ambiguity="present" if "because" not in lower else "mixed",
            generalizability="limited" if evidence_class != "broad_benchmark" else "moderate",
            relevance="high",
        )

    def _freshness(self, evidence_brief: EvidenceBriefArtifact) -> str:
        if evidence_brief.freshness_notes:
            note = " ".join(evidence_brief.freshness_notes).lower()
            if "fresh" in note:
                return "fresh"
            if "recent" in note:
                return "recent"
        return "unknown"

    def _normalize(self, text: str) -> str:
        return " ".join(re.split(r"[^a-z0-9]+", text.lower())).strip()

    def _token_set(self, text: str) -> Set[str]:
        return {
            token for token in self._normalize(text).split()
            if len(token) > 2 and token not in {"the", "and", "with", "that", "this", "from", "into", "than"}
        }

    def _claim_fingerprint(self, text: str) -> str:
        tokens = sorted(self._token_set(text))
        return " ".join(tokens[:8])

    def _support_fingerprints(self, entry: ClaimLedgerEntry) -> Set[str]:
        fingerprints = {
            self._claim_fingerprint(item)
            for item in entry.supporting_evidence
            if self._claim_fingerprint(item)
        }
        if entry.claim_fingerprint:
            fingerprints.add(entry.claim_fingerprint)
        return fingerprints

    def _similarity(self, left: ClaimLedgerEntry, right: ClaimLedgerEntry) -> float:
        token_score = 0.0
        for left_text in self._entry_text_variants(left):
            for right_text in self._entry_text_variants(right):
                left_tokens = self._token_set(left_text)
                right_tokens = self._token_set(right_text)
                if not left_tokens or not right_tokens:
                    continue
                intersection = left_tokens & right_tokens
                union = left_tokens | right_tokens
                token_score = max(token_score, len(intersection) / max(len(union), 1))

        left_support = self._support_fingerprints(left)
        right_support = self._support_fingerprints(right)
        support_score = 0.0
        if left_support and right_support:
            support_score = len(left_support & right_support) / max(len(left_support | right_support), 1)

        numeric_overlap = 0.0
        left_numbers = set(re.findall(r"\d[\d,.%]*", left.claim_text))
        right_numbers = set(re.findall(r"\d[\d,.%]*", right.claim_text))
        if left_numbers and right_numbers and left_numbers & right_numbers:
            numeric_overlap = 0.15

        return max(token_score, support_score + numeric_overlap)

    def _consolidate_claims(self, claims: List[ClaimLedgerEntry]) -> List[ClaimLedgerEntry]:
        consolidated: List[ClaimLedgerEntry] = []
        for entry in claims:
            matched = None
            for existing in consolidated:
                if self._similarity(existing, entry) >= 0.5:
                    matched = existing
                    break

            if matched is None:
                if not entry.canonical_claim_text:
                    entry.canonical_claim_text = entry.claim_text
                if not entry.claim_fingerprint:
                    entry.claim_fingerprint = self._claim_fingerprint(entry.claim_text)
                consolidated.append(entry)
                continue

            matched.duplicate_count += 1
            matched.confidence = max(matched.confidence, entry.confidence)
            matched.contested = matched.contested or entry.contested
            matched.validation_passed = (
                matched.validation_passed
                if matched.validation_passed is False
                else entry.validation_passed
            )
            matched.source_provenance = self._merge_unique(matched.source_provenance, entry.source_provenance)
            matched.supporting_evidence = self._merge_unique(matched.supporting_evidence, entry.supporting_evidence)
            matched.citation_links = self._merge_unique(matched.citation_links, entry.citation_links)
            matched.dependencies = self._merge_unique(matched.dependencies, entry.dependencies)
            matched.report_sections = self._merge_unique(matched.report_sections, entry.report_sections)
            matched.alternate_phrasings = self._merge_unique(
                matched.alternate_phrasings + [matched.claim_text],
                [entry.claim_text],
            )

            strongest_text = max(
                [matched.canonical_claim_text or matched.claim_text, entry.claim_text],
                key=lambda item: (len(self._token_set(item)), len(item)),
            )
            matched.canonical_claim_text = strongest_text
            matched.claim_text = strongest_text
            matched.claim_fingerprint = self._claim_fingerprint(strongest_text)

        return consolidated

    def _assign_section_ownership(
        self,
        claims: List[ClaimLedgerEntry],
        intent: ReportIntentArtifact,
        schema_sections: Sequence[str],
    ) -> None:
        narrative_sections = [
            title for title in schema_sections
            if title not in {
                "What Is Verified",
                "What Is Inferred",
                "Constraints and Dependencies",
                "Missing Critical Inputs",
                "Quantitative Checks",
                "What Would Change the Conclusion",
                "Sources",
                "Uncertainties and Blind Spots",
                "Methodology Note",
                "Run Trace",
            }
        ]
        if not narrative_sections:
            narrative_sections = ["Core Thesis and Confidence"]

        top_summary_claims = sorted(
            claims,
            key=lambda item: (item.confidence, item.verification_status.startswith("verified"), item.duplicate_count),
            reverse=True,
        )[:2]
        top_summary_ids = {entry.claim_id for entry in top_summary_claims}

        for entry in claims:
            target = self._best_section_for_claim(entry, narrative_sections, intent)
            entry.primary_section = target
            entry.report_sections = [target]
            if entry.claim_id in top_summary_ids and "Bottom Line" in narrative_sections and target != "Bottom Line":
                entry.report_sections = ["Bottom Line", target]

    def _best_section_for_claim(
        self,
        entry: ClaimLedgerEntry,
        narrative_sections: Sequence[str],
        intent: ReportIntentArtifact,
    ) -> str:
        lower_claim = entry.claim_text.lower()
        for section in narrative_sections:
            section_lower = section.lower()
            if "bottom line" in section_lower and entry.confidence >= 0.7 and entry.verification_status.startswith("verified"):
                return section
            if any(token in section_lower for token in ["alternative", "risk", "open questions"]) and (
                entry.contested or entry.claim_category in {"assumption", "inferred"}
            ):
                return section
            if any(token in section_lower for token in ["drivers", "signals", "evidence", "benchmark", "competitor"]) and (
                entry.claim_category == "numeric"
                or any(token in lower_claim for token in ["market", "pricing", "benchmark", "adoption", "growth", "share"])
            ):
                return section
            if any(token in section_lower for token in ["market structure", "segments"]) and any(
                token in lower_claim for token in ["market", "segment", "landscape", "distribution"]
            ):
                return section
            if any(token in section_lower for token in ["scope", "regulatory", "policy"]) and any(
                token in lower_claim for token in ["regulation", "policy", "compliance", "rule"]
            ):
                return section
        if "Bottom Line" in narrative_sections and entry.confidence >= 0.8:
            return "Bottom Line"
        return narrative_sections[min(1, len(narrative_sections) - 1)]

    def _merge_unique(self, left: List[str], right: List[str]) -> List[str]:
        merged = []
        seen = set()
        for item in [*left, *right]:
            normalized = item.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(item)
        return merged

    def _entry_text_variants(self, entry: ClaimLedgerEntry) -> List[str]:
        variants = [entry.canonical_claim_text, entry.claim_text, *entry.alternate_phrasings]
        return [variant for variant in variants if variant]
