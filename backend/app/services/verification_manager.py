"""
Claim-level verification management.
"""

from typing import List

from .claim_ledger import ClaimLedgerBuilder
from .report_artifacts import ClaimLedgerEntry, SearchPlanQuery
from .search_service import SearchService


class VerificationManager:
    def __init__(self, search_service: SearchService = None):
        self.search_service = search_service or SearchService()
        self.claim_ledger_builder = ClaimLedgerBuilder()

    def verify_claims(
        self,
        claim_ledger: List[ClaimLedgerEntry],
        search_plan: List[SearchPlanQuery],
    ) -> List[ClaimLedgerEntry]:
        for entry in claim_ledger:
            if "source_document" in entry.source_provenance and "web_evidence" not in entry.source_provenance:
                entry.verification_status = "verified_by_source_material"
                entry.validation_passed = True
                continue

            entry.externally_searched = True
            result = self.search_service.fact_check(entry.claim_text)
            entry.citation_links = list({
                *(entry.citation_links or []),
                *[cite.url for cite in result.supporting_sources[:3] if getattr(cite, "url", None)],
                *[cite.url for cite in result.contradicting_sources[:3] if getattr(cite, "url", None)],
            })

            if result.verdict == "supported" and result.confidence >= 0.55 and result.supporting_sources:
                entry.verification_status = "verified_by_external_search"
                entry.validation_passed = True
                entry.confidence = min(0.98, entry.confidence + 0.1)
            elif result.verdict == "contradicted" and result.confidence >= 0.55 and result.contradicting_sources:
                entry.verification_status = "contradicted_by_external_search"
                entry.validation_passed = False
                entry.contested = True
                entry.confidence = max(0.05, entry.confidence - 0.25)
            else:
                entry.verification_status = "unresolved"
                entry.validation_passed = None

        return claim_ledger
