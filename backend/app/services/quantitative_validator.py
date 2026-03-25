"""
Deterministic quantitative validation for report output.
"""

import re
from typing import List

from .report_artifacts import ClaimLedgerEntry, QuantitativeCheckArtifact


class QuantitativeValidator:
    def validate(self, sections: List[dict], claim_ledger: List[ClaimLedgerEntry]) -> List[QuantitativeCheckArtifact]:
        checks: List[QuantitativeCheckArtifact] = []
        full_text = "\n".join(section.get("content", "") for section in sections)

        checks.extend(self._validate_percentage_sums(full_text))
        checks.extend(self._validate_growth_claims(full_text))
        checks.extend(self._validate_cross_section_consistency(sections))
        checks.extend(self._validate_revenue_ceiling(full_text))

        numeric_claims = [entry for entry in claim_ledger if entry.claim_category == "numeric"]
        if numeric_claims:
            unresolved = [entry.claim_id for entry in numeric_claims if entry.validation_passed is False]
            checks.append(
                QuantitativeCheckArtifact(
                    name="numeric_claim_coverage",
                    status="pass" if not unresolved else "warn",
                    details=f"Tracked {len(numeric_claims)} numeric ledger claim(s).",
                    related_claims=[entry.claim_id for entry in numeric_claims],
                )
            )

        return checks

    def _validate_percentage_sums(self, text: str) -> List[QuantitativeCheckArtifact]:
        checks = []
        for line in text.splitlines():
            percents = [float(match) for match in re.findall(r"(\d+(?:\.\d+)?)%", line)]
            if len(percents) >= 2:
                total = sum(percents)
                if 99 <= total <= 101:
                    checks.append(
                        QuantitativeCheckArtifact(
                            name="percentage_sum",
                            status="pass",
                            details=f"Percentages reconcile to {total:.1f}% in: {line[:120]}",
                        )
                    )
                elif total > 101.5:
                    checks.append(
                        QuantitativeCheckArtifact(
                            name="percentage_sum",
                            status="fail",
                            details=f"Percentages sum to {total:.1f}% in: {line[:120]}",
                        )
                    )
        return checks

    def _validate_growth_claims(self, text: str) -> List[QuantitativeCheckArtifact]:
        checks = []
        pattern = re.compile(
            r"from\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\s+\((\d+(?:\.\d+)?)%\)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            start = float(match.group(1))
            end = float(match.group(2))
            stated = float(match.group(3))
            if start == 0:
                continue
            actual = ((end - start) / start) * 100
            delta = abs(actual - stated)
            status = "pass" if delta <= 1.0 else "fail"
            checks.append(
                QuantitativeCheckArtifact(
                    name="growth_reconciliation",
                    status=status,
                    details=f"Growth from {start:g} to {end:g} implies {actual:.1f}%, stated {stated:.1f}%.",
                )
            )
        return checks

    def _validate_cross_section_consistency(self, sections: List[dict]) -> List[QuantitativeCheckArtifact]:
        seen = {}
        checks = []
        for section in sections:
            title = section.get("title", "")
            content = section.get("content", "")
            for value in re.findall(r"\b\d+(?:\.\d+)?%?\b", content):
                seen.setdefault(value, []).append(title)

        repeated = {value: titles for value, titles in seen.items() if len(titles) > 1}
        if repeated:
            checks.append(
                QuantitativeCheckArtifact(
                    name="cross_section_numeric_consistency",
                    status="pass",
                    details=f"Repeated numeric anchors observed across sections: {', '.join(list(repeated.keys())[:5])}",
                )
            )
        else:
            checks.append(
                QuantitativeCheckArtifact(
                    name="cross_section_numeric_consistency",
                    status="warn",
                    details="Few shared numeric anchors were found across sections; cross-checking remains limited.",
                )
            )
        return checks

    def _validate_revenue_ceiling(self, text: str) -> List[QuantitativeCheckArtifact]:
        checks = []
        monthly_prices = []
        for match in re.finditer(
            r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:-|–|to)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/|per\s+)(?:month|mo)\b",
            text,
            re.IGNORECASE,
        ):
            monthly_prices.append((self._to_number(match.group(1)), self._to_number(match.group(2))))

        if not monthly_prices:
            return checks

        account_candidates = []
        for match in re.finditer(
            r"(?P<context>(?:(?:top|target(?:ing)?|outreach to|focus on|priorit(?:y|ize)|accounts? from)[^.\n]{0,24})?)"
            r"\b"
            r"(?P<count>\d[\d,]*)\+?\s+(?P<descriptor>(?:[a-zA-Z][a-zA-Z0-9-]*\s+){0,4})?"
            r"(?P<label>brand accounts|accounts|brands|customers|logos)\b",
            text,
            re.IGNORECASE,
        ):
            count = int(match.group("count").replace(",", ""))
            context = (match.group("context") or "").lower()
            label = match.group("label").lower()
            priority = 0 if any(token in context for token in ["top", "target", "outreach", "focus"]) else 1
            account_candidates.append((priority, count, label, context.strip()))

        if not account_candidates:
            return checks

        threshold_candidates = []
        for match in re.finditer(
            r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(million|billion|m|b)?\+?\s*(?:arr|annual recurring revenue)",
            text,
            re.IGNORECASE,
        ):
            threshold_candidates.append(self._with_unit(match.group(1), match.group(2)))

        monthly_floor, monthly_ceiling = max(monthly_prices, key=lambda item: item[1])
        _, selected_count, selected_label, selected_context = sorted(
            account_candidates,
            key=lambda item: (item[0], item[1] > 5000, item[1]),
        )[0]

        annualized_ceiling = selected_count * monthly_ceiling * 12
        annualized_floor = selected_count * monthly_floor * 12
        context_label = f"{selected_count} {selected_label}"
        if selected_context:
            context_label = f"{selected_context} {context_label}".strip()

        if threshold_candidates:
            threshold = max(threshold_candidates)
            if annualized_ceiling < threshold * 0.25:
                status = "fail"
            elif annualized_ceiling < threshold:
                status = "warn"
            else:
                status = "pass"
            checks.append(
                QuantitativeCheckArtifact(
                    name="addressable_revenue_ceiling",
                    status=status,
                    details=(
                        f"{context_label} at ${monthly_floor:,.0f}-${monthly_ceiling:,.0f}/month implies "
                        f"${annualized_floor:,.0f}-${annualized_ceiling:,.0f} ARR, versus a stated threshold of "
                        f"${threshold:,.0f}."
                    ),
                )
            )
            return checks

        checks.append(
            QuantitativeCheckArtifact(
                name="addressable_revenue_ceiling",
                status="warn",
                details=(
                    f"{context_label} at ${monthly_floor:,.0f}-${monthly_ceiling:,.0f}/month implies "
                    f"${annualized_floor:,.0f}-${annualized_ceiling:,.0f} ARR, but no explicit ARR threshold was found."
                ),
            )
        )
        return checks

    def _to_number(self, value: str) -> float:
        return float(value.replace(",", ""))

    def _with_unit(self, value: str, unit: str) -> float:
        base = self._to_number(value)
        normalized = (unit or "").lower()
        if normalized in {"m", "million"}:
            return base * 1_000_000
        if normalized in {"b", "billion"}:
            return base * 1_000_000_000
        return base
