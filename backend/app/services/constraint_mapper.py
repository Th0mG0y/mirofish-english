"""
Constraint mapping for major report claims.
"""

from .report_artifacts import ConstraintMapArtifact


class ConstraintMapper:
    def build(self, claim_text: str, report_type: str) -> ConstraintMapArtifact:
        lower = claim_text.lower()
        constraint_map = ConstraintMapArtifact()

        if any(token in lower for token in ["launch", "deploy", "implement", "rollout"]):
            constraint_map.operational_dependencies.append("Execution capability and implementation readiness")
            constraint_map.resource_dependencies.append("Budget and staffing capacity")

        if any(token in lower for token in ["adoption", "demand", "usage", "customer"]):
            constraint_map.adoption_dependencies.append("User demand and adoption behavior")

        if any(token in lower for token in ["platform", "api", "integration"]):
            constraint_map.platform_dependencies.append("Platform access, APIs, and integration stability")

        if any(token in lower for token in ["regulation", "policy", "compliance", "approval"]):
            constraint_map.regulatory_dependencies.append("Regulatory interpretation and compliance clearance")

        if any(token in lower for token in ["global", "regional", "country", "jurisdiction"]):
            constraint_map.geographic_dependencies.append("Jurisdiction-specific differences")

        if any(token in lower for token in ["quarter", "year", "timeline", "by ", "within "]):
            constraint_map.timing_dependencies.append("Delivery timing and dependency sequencing")

        constraint_map.enabling_conditions.append("Evidence remains directionally consistent across primary and external sources")
        constraint_map.limiting_conditions.append("Missing critical inputs or unresolved contradictions reduce confidence")

        if report_type in {"forecast", "scenario_analysis"}:
            constraint_map.enabling_conditions.append("Scenario assumptions continue to hold")
            constraint_map.limiting_conditions.append("Unexpected external shocks or behavioral shifts may invalidate the projection")

        return constraint_map
