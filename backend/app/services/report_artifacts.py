"""
Structured artifacts for the report intelligence pipeline.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _compact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, dict) and not value:
            continue
        compact[key] = value
    return compact


@dataclass
class SourceDocumentArtifact:
    title: str
    path: str = ""
    size: int = 0
    provenance: str = "source_document"
    summary: str = ""
    freshness: str = "unknown"
    date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class SearchPlanQuery:
    query: str
    reason: str
    report_question: str
    evidence_type: str
    intent: str = "discovery"
    chunk_id: str = ""
    chunk_label: str = ""
    source_chunk: str = ""
    focus_terms: List[str] = field(default_factory=list)
    overlap_key: str = ""
    produced_usable_evidence: bool = False
    citations_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class SearchExecutionArtifact:
    query: str
    intent: str
    answer: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    usable_evidence: bool = False
    source_quality_summary: Dict[str, Any] = field(default_factory=dict)
    freshness: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class ReportIntentArtifact:
    report_type: str
    main_question: str
    time_horizon: str
    simulation_mode: str
    source_priorities: List[str] = field(default_factory=list)
    fresh_external_information_required: bool = False
    output_structure: List[str] = field(default_factory=list)
    rationale: str = ""
    recency_sensitive_topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class EvidenceBriefArtifact:
    source_documents: List[SourceDocumentArtifact] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    key_claims: List[str] = field(default_factory=list)
    key_numbers: List[str] = field(default_factory=list)
    timeline_signals: List[str] = field(default_factory=list)
    major_unknowns: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    external_evidence: List[SearchExecutionArtifact] = field(default_factory=list)
    graph_facts: List[str] = field(default_factory=list)
    simulation_outputs: List[str] = field(default_factory=list)
    deliberation_outputs: List[str] = field(default_factory=list)
    provenance_notes: List[str] = field(default_factory=list)
    freshness_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_documents": [item.to_dict() for item in self.source_documents],
            "key_entities": self.key_entities,
            "key_claims": self.key_claims,
            "key_numbers": self.key_numbers,
            "timeline_signals": self.timeline_signals,
            "major_unknowns": self.major_unknowns,
            "contradictions": self.contradictions,
            "external_evidence": [item.to_dict() for item in self.external_evidence],
            "graph_facts": self.graph_facts,
            "simulation_outputs": self.simulation_outputs,
            "deliberation_outputs": self.deliberation_outputs,
            "provenance_notes": self.provenance_notes,
            "freshness_notes": self.freshness_notes,
        }


@dataclass
class RepresentativenessArtifact:
    evidence_class: str
    sample_size: str = "unknown"
    time_period: str = "unknown"
    context_specificity: str = "unknown"
    causal_ambiguity: str = "unknown"
    generalizability: str = "unknown"
    relevance: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class ConstraintMapArtifact:
    enabling_conditions: List[str] = field(default_factory=list)
    limiting_conditions: List[str] = field(default_factory=list)
    platform_dependencies: List[str] = field(default_factory=list)
    operational_dependencies: List[str] = field(default_factory=list)
    regulatory_dependencies: List[str] = field(default_factory=list)
    geographic_dependencies: List[str] = field(default_factory=list)
    resource_dependencies: List[str] = field(default_factory=list)
    adoption_dependencies: List[str] = field(default_factory=list)
    timing_dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class ClaimLedgerEntry:
    claim_id: str
    claim_text: str
    claim_category: str
    canonical_claim_text: str = ""
    claim_fingerprint: str = ""
    cluster_id: str = ""
    source_provenance: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    citation_links: List[str] = field(default_factory=list)
    confidence: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    validation_passed: Optional[bool] = None
    contested: bool = False
    externally_searched: bool = False
    verification_status: str = "unresolved"
    report_sections: List[str] = field(default_factory=list)
    primary_section: str = ""
    alternate_phrasings: List[str] = field(default_factory=list)
    duplicate_count: int = 1
    representativeness: RepresentativenessArtifact = field(
        default_factory=lambda: RepresentativenessArtifact(evidence_class="unclear_representativeness")
    )
    constraint_map: ConstraintMapArtifact = field(default_factory=ConstraintMapArtifact)
    source_freshness: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        payload = _compact_dict(asdict(self))
        payload["representativeness"] = self.representativeness.to_dict()
        payload["constraint_map"] = self.constraint_map.to_dict()
        return payload


@dataclass
class MissingCriticalInputArtifact:
    item: str
    why_it_matters: str
    dependent_conclusions: List[str] = field(default_factory=list)
    can_estimate: bool = False
    search_attempted: bool = False
    confidence_impact: str = "warn"

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class QuantitativeCheckArtifact:
    name: str
    status: str
    details: str
    related_claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class EditorialDefectArtifact:
    defect_type: str
    severity: str
    description: str
    section: str = ""
    related_claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class QualityGateArtifact:
    name: str
    status: str
    summary: str
    blocking: bool = False
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _compact_dict(asdict(self))


@dataclass
class RunTraceArtifact:
    source_inputs_used: List[str] = field(default_factory=list)
    simulation_used: bool = False
    simulation_reason: str = ""
    graph_usage: str = ""
    search_queries_run: int = 0
    search_categories: List[str] = field(default_factory=list)
    externally_verified_claims: int = 0
    unresolved_claims: int = 0
    quality_gates: List[QualityGateArtifact] = field(default_factory=list)
    major_gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_inputs_used": self.source_inputs_used,
            "simulation_used": self.simulation_used,
            "simulation_reason": self.simulation_reason,
            "graph_usage": self.graph_usage,
            "search_queries_run": self.search_queries_run,
            "search_categories": self.search_categories,
            "externally_verified_claims": self.externally_verified_claims,
            "unresolved_claims": self.unresolved_claims,
            "quality_gates": [gate.to_dict() for gate in self.quality_gates],
            "major_gaps": self.major_gaps,
        }
