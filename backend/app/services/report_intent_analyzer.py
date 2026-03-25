"""
Heuristic report intent analysis for domain-agnostic report generation.
"""

import re
from typing import Dict, List, Optional

from .report_artifacts import ReportIntentArtifact


REPORT_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "forecast": ["forecast", "predict", "projection", "outlook", "trajectory"],
    "scenario_analysis": ["scenario", "what if", "stress test", "alternative future"],
    "research_summary": ["summary", "synthesize", "literature", "research memo", "evidence memo"],
    "due_diligence": ["diligence", "acquisition", "investment", "company analysis", "thesis"],
    "market_landscape": ["market", "competitor", "landscape", "segmentation", "industry"],
    "strategy_memo": ["strategy", "go to market", "product", "positioning", "roadmap"],
    "risk_assessment": ["risk", "exposure", "failure mode", "mitigation", "operational"],
    "policy_regulatory_analysis": ["policy", "regulation", "regulatory", "compliance", "law"],
}

SIMULATION_REQUIRED_TYPES = {"forecast", "scenario_analysis"}
SIMULATION_OPTIONAL_TYPES = {"strategy_memo", "risk_assessment", "market_landscape", "due_diligence"}
RECENCY_SENSITIVE_TYPES = {
    "forecast",
    "scenario_analysis",
    "due_diligence",
    "market_landscape",
    "policy_regulatory_analysis",
    "strategy_memo",
    "risk_assessment",
}


class ReportIntentAnalyzer:
    def analyze(
        self,
        requirement: str,
        project_summary: str = "",
        document_context: str = "",
    ) -> ReportIntentArtifact:
        text = " ".join(
            part.strip()
            for part in [requirement or "", project_summary or "", document_context[:2000] or ""]
            if part and part.strip()
        )
        lower = text.lower()

        report_type = self._classify_report_type(lower)
        time_horizon = self._extract_time_horizon(lower)
        main_question = self._build_main_question(requirement)
        simulation_mode = self._simulation_mode_for(report_type, lower)
        output_structure = self._default_structure(report_type)
        recency_sensitive_topics = self._recency_topics(lower)

        return ReportIntentArtifact(
            report_type=report_type,
            main_question=main_question,
            time_horizon=time_horizon,
            simulation_mode=simulation_mode,
            source_priorities=self._source_priorities(report_type, simulation_mode),
            fresh_external_information_required=(
                report_type in RECENCY_SENSITIVE_TYPES or bool(recency_sensitive_topics)
            ),
            output_structure=output_structure,
            rationale=self._build_rationale(report_type, simulation_mode, recency_sensitive_topics),
            recency_sensitive_topics=recency_sensitive_topics,
        )

    def _classify_report_type(self, text: str) -> str:
        scores: Dict[str, int] = {}
        for report_type, keywords in REPORT_TYPE_KEYWORDS.items():
            scores[report_type] = sum(1 for keyword in keywords if keyword in text)

        best_type = max(scores, key=scores.get)
        if scores[best_type] == 0:
            return "research_summary"
        return best_type

    def _extract_time_horizon(self, text: str) -> str:
        if any(token in text for token in ["today", "current", "current state", "recent", "latest"]):
            return "current_state"
        if re.search(r"\b(next|within)\s+\d+\s+(day|days|week|weeks|month|months|year|years)\b", text):
            return "explicit_near_term"
        if re.search(r"\b20\d{2}\b", text):
            return "dated_horizon"
        if any(token in text for token in ["long term", "five year", "10 year", "decade"]):
            return "long_term"
        if any(token in text for token in ["near term", "short term", "this year", "next quarter"]):
            return "near_term"
        return "unspecified"

    def _build_main_question(self, requirement: str) -> str:
        clean = " ".join((requirement or "").split())
        if not clean:
            return "What is the most decision-relevant answer supported by the available evidence?"
        if clean.endswith("?"):
            return clean
        return f"What is the strongest evidence-based answer to: {clean}?"

    def _simulation_mode_for(self, report_type: str, text: str) -> str:
        if report_type in SIMULATION_REQUIRED_TYPES:
            return "required"
        if report_type in SIMULATION_OPTIONAL_TYPES:
            if any(token in text for token in ["stakeholder reaction", "second-order", "stress test", "reaction"]):
                return "useful_but_optional"
            return "optional"
        return "irrelevant"

    def _source_priorities(self, report_type: str, simulation_mode: str) -> List[str]:
        priorities = ["source_documents", "external_evidence", "graph_context"]
        if report_type in {"policy_regulatory_analysis", "due_diligence"}:
            priorities = ["source_documents", "external_evidence", "graph_context"]
        if report_type in {"forecast", "scenario_analysis"}:
            priorities = ["source_documents", "external_evidence", "graph_context", "simulation_outputs"]
        if simulation_mode in {"optional", "useful_but_optional", "required"}:
            priorities.append("simulation_outputs")
        priorities.append("deliberation_outputs")
        return priorities

    def _default_structure(self, report_type: str) -> List[str]:
        if report_type == "forecast":
            return [
                "Bottom Line",
                "Core Thesis and Confidence",
                "Drivers and Signals",
                "Scenarios and Alternative Paths",
                "Constraints and Dependencies",
                "What Is Verified",
                "What Is Inferred",
                "Missing Critical Inputs",
                "Quantitative Checks",
                "What Would Change the Conclusion",
                "Uncertainties and Blind Spots",
                "Methodology Note",
                "Run Trace",
            ]
        if report_type == "due_diligence":
            return [
                "Bottom Line",
                "Investment or Decision Thesis",
                "What Is Verified",
                "Key Risks and Open Questions",
                "Constraints and Dependencies",
                "What Is Inferred",
                "Missing Critical Inputs",
                "Quantitative Checks",
                "Alternative Interpretations",
                "What Would Change the Conclusion",
                "Uncertainties and Blind Spots",
                "Methodology Note",
                "Run Trace",
            ]
        if report_type == "market_landscape":
            return [
                "Bottom Line",
                "Market Structure and Segments",
                "Competitor and Benchmark Context",
                "Key Drivers and Dynamics",
                "What Is Verified",
                "What Is Inferred",
                "Constraints and Dependencies",
                "Missing Critical Inputs",
                "Quantitative Checks",
                "Alternative Interpretations",
                "What Would Change the Conclusion",
                "Methodology Note",
                "Run Trace",
            ]
        if report_type == "policy_regulatory_analysis":
            return [
                "Bottom Line",
                "Regulatory Scope and Core Thesis",
                "What Is Verified",
                "Stakeholder and Implementation Implications",
                "Constraints and Dependencies",
                "What Is Inferred",
                "Missing Critical Inputs",
                "Quantitative Checks",
                "Alternative Interpretations",
                "What Would Change the Conclusion",
                "Uncertainties and Blind Spots",
                "Methodology Note",
                "Run Trace",
            ]
        return [
            "Bottom Line",
            "Core Thesis and Confidence",
            "Key Evidence and Drivers",
            "What Is Verified",
            "What Is Inferred",
            "Constraints and Dependencies",
            "Missing Critical Inputs",
            "Quantitative Checks",
            "Alternative Interpretations or Scenarios",
            "What Would Change the Conclusion",
            "Uncertainties and Blind Spots",
            "Methodology Note",
            "Run Trace",
        ]

    def _recency_topics(self, text: str) -> List[str]:
        topics = []
        if any(token in text for token in ["regulation", "regulatory", "policy", "law"]):
            topics.append("regulation")
        if any(token in text for token in ["market", "pricing", "competitor", "launch", "funding"]):
            topics.append("market_dynamics")
        if any(token in text for token in ["macro", "geopolitical", "economy"]):
            topics.append("macro_conditions")
        if any(token in text for token in ["platform", "api", "product launch", "policy change"]):
            topics.append("platform_changes")
        return topics

    def _build_rationale(
        self,
        report_type: str,
        simulation_mode: str,
        recency_sensitive_topics: List[str],
    ) -> str:
        parts = [
            f"Classified as {report_type.replace('_', ' ')}.",
            f"Simulation is {simulation_mode.replace('_', ' ')} for this request.",
        ]
        if recency_sensitive_topics:
            parts.append(
                "Fresh external grounding is needed for "
                + ", ".join(topic.replace("_", " ") for topic in recency_sensitive_topics)
                + "."
            )
        return " ".join(parts)
