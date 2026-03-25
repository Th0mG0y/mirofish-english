"""
Build run trace summaries for report outputs.
"""

from typing import List

from .report_artifacts import (
    ClaimLedgerEntry,
    MissingCriticalInputArtifact,
    QualityGateArtifact,
    RunTraceArtifact,
)


class RunTraceBuilder:
    def build(
        self,
        source_inputs_used: List[str],
        simulation_used: bool,
        simulation_reason: str,
        graph_usage: str,
        search_plan: List[dict],
        claim_ledger: List[ClaimLedgerEntry],
        missing_inputs: List[MissingCriticalInputArtifact],
        quality_gates: List[QualityGateArtifact],
    ) -> RunTraceArtifact:
        return RunTraceArtifact(
            source_inputs_used=source_inputs_used,
            simulation_used=simulation_used,
            simulation_reason=simulation_reason,
            graph_usage=graph_usage,
            search_queries_run=len(search_plan),
            search_categories=sorted({entry.get("intent", "discovery") for entry in search_plan}),
            externally_verified_claims=sum(
                1 for entry in claim_ledger if entry.verification_status == "verified_by_external_search"
            ),
            unresolved_claims=sum(1 for entry in claim_ledger if entry.verification_status == "unresolved"),
            quality_gates=quality_gates,
            major_gaps=[item.item for item in missing_inputs],
        )
