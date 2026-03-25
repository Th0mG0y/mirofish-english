"""
Detect decision-relevant missing inputs by report type.
"""

import re
from typing import Dict, List, Optional

from .report_artifacts import (
    ClaimLedgerEntry,
    EvidenceBriefArtifact,
    MissingCriticalInputArtifact,
    ReportIntentArtifact,
)


REQUIRED_INPUTS: Dict[str, List[Dict[str, str]]] = {
    "due_diligence": [
        {
            "item": "baseline operating metrics",
            "keywords": "revenue arr mrr margin customers customer churn retention burn",
            "confidence_impact": "fail",
        },
        {
            "item": "customer concentration",
            "keywords": "top customer concentration revenue mix accounts dependence",
            "confidence_impact": "fail",
        },
        {
            "item": "implementation constraints",
            "keywords": "team resources implementation integration staffing",
            "confidence_impact": "warn",
        },
    ],
    "market_landscape": [
        {
            "item": "current revenue or traction baseline",
            "keywords": "arr mrr revenue customers customer churn retention traction logos accounts",
            "confidence_impact": "fail",
        },
        {
            "item": "market size assumptions",
            "keywords": "tam sam som market size segment category demand",
            "confidence_impact": "fail",
        },
        {
            "item": "benchmark context",
            "keywords": "benchmark pricing share growth comparison peer",
            "confidence_impact": "warn",
        },
        {
            "item": "competitive feature comparison validation",
            "keywords": "competitor compare parity feature features benchmark pricing",
            "confidence_impact": "fail",
        },
        {
            "item": "independent verification of proof points",
            "keywords": "independent benchmark published study case study reference customer testimonial verified",
            "confidence_impact": "fail",
        },
        {
            "item": "platform dependency or roadmap intelligence",
            "keywords": "roadmap native integration api platform shopify adobe salesforce",
            "confidence_impact": "warn",
        },
    ],
    "policy_regulatory_analysis": [
        {
            "item": "regulatory scope details",
            "keywords": "scope rule requirement exemption enforcement",
            "confidence_impact": "fail",
        },
        {
            "item": "geographic limitations",
            "keywords": "jurisdiction geography state country eu",
            "confidence_impact": "warn",
        },
        {
            "item": "timeline uncertainty",
            "keywords": "effective date implementation timeline transition",
            "confidence_impact": "warn",
        },
    ],
    "risk_assessment": [
        {
            "item": "baseline operating metrics",
            "keywords": "baseline incidents severity frequency",
            "confidence_impact": "fail",
        },
        {
            "item": "implementation constraints",
            "keywords": "mitigation staffing system dependencies",
            "confidence_impact": "warn",
        },
        {
            "item": "behavioral evidence",
            "keywords": "incident behavior compliance adoption",
            "confidence_impact": "warn",
        },
    ],
}


class MissingInputDetector:
    def detect(
        self,
        intent: ReportIntentArtifact,
        evidence_brief: EvidenceBriefArtifact,
        search_plan: List[Dict[str, object]] = None,
        claim_ledger: Optional[List[ClaimLedgerEntry]] = None,
    ) -> List[MissingCriticalInputArtifact]:
        search_plan = search_plan or []
        grounded_text = self._grounded_evidence_text(evidence_brief)
        unresolved_text = " ".join(
            entry.claim_text
            for entry in (claim_ledger or [])
            if entry.verification_status in {"unresolved", "contradicted_by_external_search"}
        ).lower()
        unknown_text = " ".join(
            evidence_brief.major_unknowns
            + evidence_brief.contradictions
            + evidence_brief.freshness_notes
        ).lower()

        specs = REQUIRED_INPUTS.get(intent.report_type, [])
        if not specs:
            specs = [
                {"item": "benchmark context", "keywords": "benchmark comparison peer", "confidence_impact": "warn"},
                {"item": "timeline uncertainty", "keywords": "timeline timing date", "confidence_impact": "warn"},
            ]

        missing = []
        for spec in specs:
            keywords = spec["keywords"].split()
            present = sum(1 for keyword in keywords if self._contains_keyword(grounded_text, keyword))
            unresolved_related = sum(1 for keyword in keywords if self._contains_keyword(unresolved_text, keyword))
            explicit_unknown = any(self._contains_keyword(unknown_text, keyword) for keyword in keywords)

            if present >= 2 and unresolved_related == 0 and not explicit_unknown:
                continue

            search_attempted = any(
                any(keyword in str(query.get("query", "")).lower() for keyword in keywords[:3])
                or query.get("intent") == "missing_input"
                for query in search_plan
            )
            missing.append(
                MissingCriticalInputArtifact(
                    item=spec["item"],
                    why_it_matters=f"The report depends on {spec['item']} to support high-confidence conclusions.",
                    dependent_conclusions=[intent.main_question],
                    can_estimate=spec.get("can_estimate", spec["item"] in {"benchmark context", "timeline uncertainty"}),
                    search_attempted=search_attempted,
                    confidence_impact=spec.get(
                        "confidence_impact",
                        "fail" if intent.report_type in {"due_diligence", "policy_regulatory_analysis"} else "warn",
                    ),
                )
            )

        return missing

    def _grounded_evidence_text(self, evidence_brief: EvidenceBriefArtifact) -> str:
        citation_text = []
        for evidence in evidence_brief.external_evidence:
            for citation in evidence.citations:
                citation_text.append(" ".join([
                    str(citation.get("title", "")),
                    str(citation.get("snippet", "")),
                    str(citation.get("url", "")),
                ]))

        return " ".join(
            evidence_brief.key_numbers
            + evidence_brief.timeline_signals
            + evidence_brief.graph_facts
            + evidence_brief.simulation_outputs
            + evidence_brief.deliberation_outputs
            + [document.summary for document in evidence_brief.source_documents]
            + [evidence.answer for evidence in evidence_brief.external_evidence if evidence.usable_evidence]
            + citation_text
        ).lower()

    def _contains_keyword(self, text: str, keyword: str) -> bool:
        return bool(re.search(rf"\b{re.escape(keyword.lower())}\b", text))
