"""
Evaluate report quality gates before finalization.
"""

from typing import List

from .report_artifacts import (
    ClaimLedgerEntry,
    EditorialDefectArtifact,
    MissingCriticalInputArtifact,
    QualityGateArtifact,
    QuantitativeCheckArtifact,
)


class QualityGateEvaluator:
    def evaluate(
        self,
        claim_ledger: List[ClaimLedgerEntry],
        missing_inputs: List[MissingCriticalInputArtifact],
        quantitative_checks: List[QuantitativeCheckArtifact],
        editorial_defects: List[EditorialDefectArtifact],
    ) -> List[QualityGateArtifact]:
        gates: List[QualityGateArtifact] = []

        unsupported_claims = [
            entry.claim_id for entry in claim_ledger
            if entry.verification_status in {"unresolved", "contradicted_by_external_search"}
        ]
        gates.append(
            QualityGateArtifact(
                name="claim_support",
                status="fail" if len(unsupported_claims) >= 3 else ("warn" if unsupported_claims else "pass"),
                summary="Check whether major claims are verified or still unresolved.",
                blocking=len(unsupported_claims) >= 3,
                details=unsupported_claims[:8],
            )
        )

        failed_quant = [check.details for check in quantitative_checks if check.status == "fail"]
        gates.append(
            QualityGateArtifact(
                name="quantitative_validation",
                status="fail" if failed_quant else "pass",
                summary="Deterministic numeric validation and reconciliation.",
                blocking=bool(failed_quant),
                details=failed_quant[:8],
            )
        )

        severe_missing = [item.item for item in missing_inputs if item.confidence_impact == "fail"]
        gates.append(
            QualityGateArtifact(
                name="missing_critical_inputs",
                status="warn" if missing_inputs else "pass",
                summary="Ensure major gaps are surfaced instead of buried.",
                blocking=False,
                details=severe_missing or [item.item for item in missing_inputs[:8]],
            )
        )

        blocking_editorial = [
            defect.description
            for defect in editorial_defects
            if defect.defect_type in {"formatting_artifact", "truncated_section"}
        ]
        severe_editorial = [defect.description for defect in editorial_defects if defect.severity == "warning"]
        gates.append(
            QualityGateArtifact(
                name="editorial_consistency",
                status="fail" if blocking_editorial else ("warn" if severe_editorial else "pass"),
                summary="Check for repetition, shallow sections, and unsupported framing.",
                blocking=bool(blocking_editorial),
                details=(blocking_editorial or severe_editorial)[:8],
            )
        )

        provenance_gaps = [
            entry.claim_id for entry in claim_ledger
            if "unresolved" in entry.source_provenance or not entry.source_provenance
        ]
        gates.append(
            QualityGateArtifact(
                name="provenance_coverage",
                status="warn" if provenance_gaps else "pass",
                summary="Ensure claims carry provenance labels.",
                blocking=False,
                details=provenance_gaps[:8],
            )
        )

        return gates
