"""
Schema registry for type-aware report planning.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .report_artifacts import ReportIntentArtifact


@dataclass
class SchemaSection:
    key: str
    title: str
    description: str
    render_mode: str = "narrative"
    required_evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, str]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "render_mode": self.render_mode,
            "required_evidence": self.required_evidence,
        }


@dataclass
class ReportSchema:
    key: str
    title_prefix: str
    sections: List[SchemaSection]

    def to_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "title_prefix": self.title_prefix,
            "sections": [section.to_dict() for section in self.sections],
        }


class ReportSchemaRegistry:
    def __init__(self):
        self._schemas = self._build_schemas()

    def get_schema(self, intent: ReportIntentArtifact) -> ReportSchema:
        return self._schemas.get(intent.report_type, self._schemas["research_summary"])

    def _build_schemas(self) -> Dict[str, ReportSchema]:
        base_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="State the most decision-relevant answer in a concise form.",
                required_evidence=["key_claims", "external_evidence"],
            ),
            SchemaSection(
                key="verified",
                title="What Is Verified",
                description="Summarize claims that are directly supported by uploaded material or external evidence.",
                render_mode="structured",
                required_evidence=["claim_ledger"],
            ),
            SchemaSection(
                key="inferred",
                title="What Is Inferred",
                description="Separate synthesis and inference from direct verification.",
                render_mode="structured",
                required_evidence=["claim_ledger"],
            ),
            SchemaSection(
                key="constraints",
                title="Constraints and Dependencies",
                description="Map the conditions that must hold for the thesis to remain valid.",
                render_mode="structured",
                required_evidence=["claim_ledger"],
            ),
            SchemaSection(
                key="missing_inputs",
                title="Missing Critical Inputs",
                description="Surface unresolved decision-relevant gaps.",
                render_mode="structured",
                required_evidence=["missing_inputs"],
            ),
            SchemaSection(
                key="quant_checks",
                title="Quantitative Checks",
                description="Report deterministic numeric validation and reconciliation results.",
                render_mode="structured",
                required_evidence=["quantitative_checks"],
            ),
            SchemaSection(
                key="what_changes",
                title="What Would Change the Conclusion",
                description="Explain the data or developments most likely to change the conclusion.",
                render_mode="structured",
                required_evidence=["missing_inputs", "claim_ledger"],
            ),
            SchemaSection(
                key="sources",
                title="Sources",
                description="Summarize the main evidence sources used in the report.",
                render_mode="structured",
                required_evidence=["source_documents", "external_evidence"],
            ),
            SchemaSection(
                key="uncertainties",
                title="Uncertainties and Blind Spots",
                description="Make limits, weak evidence, and unresolved contradictions explicit.",
                render_mode="structured",
                required_evidence=["missing_inputs", "quality_gates"],
            ),
            SchemaSection(
                key="methodology",
                title="Methodology Note",
                description="Explain how documents, graph retrieval, search, and optional simulation were used.",
                render_mode="structured",
                required_evidence=["run_trace"],
            ),
            SchemaSection(
                key="run_trace",
                title="Run Trace",
                description="Summarize search, verification, and quality gate execution.",
                render_mode="structured",
                required_evidence=["run_trace"],
            ),
        ]

        def compose(title_prefix: str, middle_sections: List[SchemaSection]) -> List[SchemaSection]:
            return [middle_sections[0], *middle_sections[1:], *base_sections[1:]]

        forecast_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="State the most decision-relevant forecast answer and headline confidence.",
            ),
            SchemaSection(
                key="core_thesis",
                title="Core Thesis and Confidence",
                description="Describe the forecast thesis, confidence level, and leading assumptions.",
                required_evidence=["key_claims", "external_evidence", "simulation_outputs"],
            ),
            SchemaSection(
                key="drivers",
                title="Drivers and Signals",
                description="Explain the strongest drivers, signals, and trend evidence.",
                required_evidence=["key_numbers", "timeline_signals", "external_evidence"],
            ),
            SchemaSection(
                key="alternatives",
                title="Alternative Interpretations or Scenarios",
                description="Show alternative pathways, counterevidence, and scenario ranges.",
                required_evidence=["external_evidence", "simulation_outputs"],
            ),
        ]

        diligence_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="Give the overall diligence conclusion and confidence.",
            ),
            SchemaSection(
                key="core_thesis",
                title="Investment or Decision Thesis",
                description="State the thesis that survives verification.",
                required_evidence=["key_claims", "external_evidence", "graph_facts"],
            ),
            SchemaSection(
                key="risks",
                title="Key Risks and Open Questions",
                description="Highlight risks, contested claims, and gaps requiring diligence follow-up.",
                required_evidence=["missing_inputs", "contradictions"],
            ),
            SchemaSection(
                key="alternatives",
                title="Alternative Interpretations",
                description="Surface counterarguments and disconfirming evidence.",
                required_evidence=["external_evidence", "claim_ledger"],
            ),
        ]

        market_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="Summarize the most important market conclusion.",
            ),
            SchemaSection(
                key="market_structure",
                title="Market Structure and Segments",
                description="Describe the market segments, boundaries, and benchmarks.",
                required_evidence=["external_evidence", "graph_facts"],
            ),
            SchemaSection(
                key="competitors",
                title="Competitor and Benchmark Context",
                description="Compare competitors, pricing, positioning, or other benchmarks.",
                required_evidence=["external_evidence", "key_numbers"],
            ),
            SchemaSection(
                key="drivers",
                title="Key Drivers and Dynamics",
                description="Explain the demand, supply, adoption, or regulatory forces shaping the landscape.",
                required_evidence=["external_evidence", "timeline_signals"],
            ),
        ]

        policy_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="Summarize the policy or regulatory answer and its implications.",
            ),
            SchemaSection(
                key="scope",
                title="Regulatory Scope and Core Thesis",
                description="State what the policy appears to cover and the main interpretation.",
                required_evidence=["external_evidence", "source_documents"],
            ),
            SchemaSection(
                key="implications",
                title="Stakeholder and Implementation Implications",
                description="Describe implications for operators, users, or other stakeholders.",
                required_evidence=["claim_ledger", "external_evidence", "simulation_outputs"],
            ),
            SchemaSection(
                key="alternatives",
                title="Alternative Interpretations",
                description="Call out plausible alternative readings, edge cases, and counterevidence.",
                required_evidence=["external_evidence", "claim_ledger"],
            ),
        ]

        research_sections = [
            SchemaSection(
                key="bottom_line",
                title="Bottom Line",
                description="Summarize the strongest supported answer.",
            ),
            SchemaSection(
                key="core_thesis",
                title="Core Thesis and Confidence",
                description="State the main answer and its support level.",
                required_evidence=["claim_ledger", "external_evidence"],
            ),
            SchemaSection(
                key="evidence",
                title="Key Evidence and Drivers",
                description="Explain the strongest supporting and contradicting evidence.",
                required_evidence=["external_evidence", "graph_facts", "key_numbers"],
            ),
            SchemaSection(
                key="alternatives",
                title="Alternative Interpretations or Scenarios",
                description="Explain plausible alternative explanations or future branches.",
                required_evidence=["claim_ledger", "external_evidence"],
            ),
        ]

        return {
            "forecast": ReportSchema("forecast", "Forecast Report", compose("Forecast Report", forecast_sections)),
            "scenario_analysis": ReportSchema("scenario_analysis", "Scenario Report", compose("Scenario Report", forecast_sections)),
            "due_diligence": ReportSchema("due_diligence", "Diligence Report", compose("Diligence Report", diligence_sections)),
            "market_landscape": ReportSchema("market_landscape", "Market Report", compose("Market Report", market_sections)),
            "policy_regulatory_analysis": ReportSchema("policy_regulatory_analysis", "Policy Report", compose("Policy Report", policy_sections)),
            "strategy_memo": ReportSchema("strategy_memo", "Strategy Report", compose("Strategy Report", research_sections)),
            "risk_assessment": ReportSchema("risk_assessment", "Risk Report", compose("Risk Report", research_sections)),
            "research_summary": ReportSchema("research_summary", "Research Report", compose("Research Report", research_sections)),
        }
