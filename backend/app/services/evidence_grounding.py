"""
Evidence Grounding
SNN-inspired evidence grounding and hallucination detection.
Ported from brain-in-the-fish snn.rs — simplified Python scoring logic
without neurons or firing dynamics. Core principle: claims without evidence get no score.
"""

import math
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger('mirofish.evidence_grounding')


@dataclass
class EvidenceItem:
    source: str
    text: str
    is_quantified: bool = False
    strength: float = 0.5  # 0-1

    def to_dict(self):
        return {
            "source": self.source,
            "text": self.text,
            "is_quantified": self.is_quantified,
            "strength": round(self.strength, 3),
        }


@dataclass
class GroundingScore:
    score: float = 0.0               # 0-1
    confidence: float = 0.0          # 0-1
    evidence_count: int = 0
    grounded: bool = False
    confidence_interval: Tuple[float, float] = (0.0, 1.0)
    hallucination_risk: bool = False
    explanation: str = ""

    def to_dict(self):
        return {
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "evidence_count": self.evidence_count,
            "grounded": self.grounded,
            "confidence_interval": [
                round(self.confidence_interval[0], 3),
                round(self.confidence_interval[1], 3),
            ],
            "hallucination_risk": self.hallucination_risk,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Core grounding assessment
# ---------------------------------------------------------------------------

def assess_grounding(claim: str, evidence: List[EvidenceItem]) -> GroundingScore:
    """
    Assess how well a claim is grounded in evidence.

    Core SNN principle: no evidence -> score=0, grounded=False.
    With evidence, score is based on:
      - evidence_saturation (log scale, 50% weight)
      - spike_quality (average strength, 35% weight)
      - quantified_ratio (% of quantified evidence, 15% weight)
    """
    count = len(evidence)

    if count == 0:
        # Core SNN principle: no evidence = no score
        has_confident_language = any(
            w in claim.lower()
            for w in ["clearly", "obviously", "certainly", "undoubtedly", "proves"]
        )
        return GroundingScore(
            score=0.0,
            confidence=0.0,
            evidence_count=0,
            grounded=False,
            confidence_interval=(0.0, 1.0),
            hallucination_risk=has_confident_language,
            explanation=(
                "No evidence found to support this claim. "
                + ("Hallucination risk: claim uses confident language without evidence basis."
                   if has_confident_language else "Score cannot be computed without evidence.")
            ),
        )

    # Evidence saturation: log scale so diminishing returns
    # ln(1+count) / ln(16), capped at 1.0
    evidence_saturation = min(1.0, math.log(1 + count) / math.log(16))

    # Spike quality: average strength of evidence items
    spike_quality = sum(e.strength for e in evidence) / count

    # Quantified ratio
    quantified_count = sum(1 for e in evidence if e.is_quantified)
    quantified_ratio = quantified_count / count

    # Weighted combination
    raw_score = min(1.0, (
        evidence_saturation * 0.50
        + spike_quality * 0.35
        + quantified_ratio * 0.15
    ))

    # Confidence: volume + quality
    volume_confidence = min(1.0, count / 5.0)
    confidence = min(1.0, volume_confidence * 0.5 + spike_quality * 0.5)

    # Confidence interval: narrows with more evidence
    if count == 0:
        ci_width = 1.0
    elif count < 3:
        ci_width = 0.4
    elif count < 5:
        ci_width = 0.25
    elif count < 10:
        ci_width = 0.15
    else:
        ci_width = 0.08

    ci_low = max(0.0, raw_score - ci_width / 2)
    ci_high = min(1.0, raw_score + ci_width / 2)

    explanation = (
        f"Grounding score: {raw_score:.2f} (CI: {ci_low:.2f}-{ci_high:.2f}). "
        f"{count} evidence items ({quantified_count} quantified). "
        f"Avg strength: {spike_quality:.2f}. Confidence: {confidence:.0%}."
    )

    return GroundingScore(
        score=raw_score,
        confidence=confidence,
        evidence_count=count,
        grounded=True,
        confidence_interval=(ci_low, ci_high),
        hallucination_risk=False,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Hallucination detection
# ---------------------------------------------------------------------------

def detect_hallucination_risk(
    llm_score: float,
    evidence_score: float,
    max_score: float = 1.0,
) -> bool:
    """
    Detect hallucination risk by comparing LLM confidence vs evidence support.

    If LLM says >70% but evidence says <30%, the LLM may be hallucinating.
    Ported from snn.rs blend_scores.
    """
    llm_norm = llm_score / max_score if max_score > 0 else 0
    ev_norm = evidence_score / max_score if max_score > 0 else 0
    return llm_norm > 0.7 and ev_norm < 0.3


# ---------------------------------------------------------------------------
# Claim tagging
# ---------------------------------------------------------------------------

def tag_unverified_claims(
    text: str,
    evidence_texts: List[str],
) -> str:
    """
    Tag each claim-containing sentence with evidence grounding status.

    Extends existing [UNVERIFIED -- SIMULATION-DERIVED] tagging convention.

    Tags applied:
      - [EVIDENCE-GROUNDED] — keyword overlap >= 0.3 with evidence
      - [PARTIALLY-GROUNDED] — keyword overlap >= 0.15
      - [UNVERIFIED -- SIMULATION-DERIVED] — no supporting evidence

    Only sentences containing claims/predictions are tagged (detected via
    assertive language patterns).
    """
    from .credibility_assessor import extract_keywords, keyword_overlap

    # Pre-compute evidence keywords
    evidence_kw = [extract_keywords(et.lower()) for et in evidence_texts]

    sentences = re.split(r'(?<=[.!?])\s+', text)
    tagged_sentences = []

    claim_indicators = [
        "will", "would", "could", "should", "expect", "predict",
        "increase", "decrease", "reduce", "achieve", "improve",
        "grow", "target", "estimate", "forecast", "project",
    ]

    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            tagged_sentences.append(stripped)
            continue

        lower = stripped.lower()

        # Skip if already tagged
        if "[EVIDENCE-GROUNDED]" in stripped or "[UNVERIFIED" in stripped or "[PARTIALLY-GROUNDED]" in stripped:
            tagged_sentences.append(stripped)
            continue

        # Only tag claim-like sentences
        is_claim = any(ind in lower for ind in claim_indicators) and len(stripped) > 30

        if not is_claim:
            tagged_sentences.append(stripped)
            continue

        # Check evidence support via keyword overlap
        sent_kw = extract_keywords(lower)
        if not sent_kw:
            tagged_sentences.append(stripped)
            continue

        best_overlap = 0.0
        for ev_kw in evidence_kw:
            overlap = keyword_overlap(sent_kw, ev_kw)
            best_overlap = max(best_overlap, overlap)

        if best_overlap >= 0.3:
            tagged_sentences.append(f"{stripped} [EVIDENCE-GROUNDED]")
        elif best_overlap >= 0.15:
            tagged_sentences.append(f"{stripped} [PARTIALLY-GROUNDED]")
        else:
            tagged_sentences.append(f"{stripped} [UNVERIFIED -- SIMULATION-DERIVED]")

    return " ".join(tagged_sentences)


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------

def grounding_summary(scores: List[Tuple[str, GroundingScore]]) -> str:
    """Generate a markdown summary of grounding scores for a set of claims."""
    if not scores:
        return ""

    grounded = sum(1 for _, s in scores if s.grounded)
    risky = sum(1 for _, s in scores if s.hallucination_risk)

    lines = [
        "\n### Evidence Grounding Summary\n",
        f"{len(scores)} claim(s) assessed: "
        f"{grounded} grounded, {len(scores) - grounded} ungrounded"
        f"{f', {risky} with hallucination risk' if risky else ''}.\n",
    ]

    for claim_text, score in scores:
        snippet = claim_text[:70] + "..." if len(claim_text) > 70 else claim_text
        status = "GROUNDED" if score.grounded else "UNGROUNDED"
        risk_flag = " [HALLUCINATION RISK]" if score.hallucination_risk else ""
        lines.append(
            f"- **{status}**{risk_flag} ({score.score:.0%}, "
            f"CI: {score.confidence_interval[0]:.0%}-{score.confidence_interval[1]:.0%}): "
            f"{snippet}"
        )

    lines.append("")
    return "\n".join(lines)
