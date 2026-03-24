"""
Credibility Assessor
Extracts predictions/claims from text and assesses credibility based on evidence.
Ported from brain-in-the-fish predict.rs — pure Python, no Rust dependency.
"""

import re
import uuid
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger('mirofish.credibility_assessor')


class PredictionType(str, Enum):
    QUANTITATIVE_TARGET = "quantitative_target"
    QUALITATIVE_GOAL = "qualitative_goal"
    TIMELINE = "timeline"
    COST_ESTIMATE = "cost_estimate"
    COMPARISON_CLAIM = "comparison_claim"
    COMMITMENT = "commitment"


class CredibilityVerdict(str, Enum):
    WELL_SUPPORTED = "well_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    ASPIRATIONAL = "aspirational"
    UNSUPPORTED = "unsupported"
    OVER_CLAIMED = "over_claimed"


@dataclass
class CredibilityAssessment:
    score: float = 0.0               # 0.0-1.0
    confidence: float = 0.0          # 0.0-1.0
    supporting_evidence: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    verdict: CredibilityVerdict = CredibilityVerdict.UNSUPPORTED
    explanation: str = ""

    def to_dict(self):
        return {
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "supporting_evidence": self.supporting_evidence,
            "risk_factors": self.risk_factors,
            "verdict": self.verdict.value,
            "explanation": self.explanation
        }


@dataclass
class Prediction:
    text: str
    prediction_type: PredictionType
    target_value: Optional[str] = None
    timeframe: Optional[str] = None
    section_title: str = ""
    credibility: CredibilityAssessment = field(default_factory=CredibilityAssessment)
    prediction_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    def to_dict(self):
        return {
            "prediction_id": self.prediction_id,
            "text": self.text,
            "prediction_type": self.prediction_type.value,
            "target_value": self.target_value,
            "timeframe": self.timeframe,
            "section_title": self.section_title,
            "credibility": self.credibility.to_dict()
        }


# ---------------------------------------------------------------------------
# Stopwords for keyword extraction
# ---------------------------------------------------------------------------
STOPWORDS = frozenset([
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "is",
    "are", "was", "were", "be", "will", "would", "could", "should", "may",
    "might", "this", "that", "with", "from", "by", "as", "it", "not",
    "has", "have", "had", "been", "its", "their", "they", "we", "our",
    "but", "all", "also", "than", "more", "can", "do", "did", "does",
])


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------

def extract_keywords(text: str) -> List[str]:
    """Split text into lowercase keywords, filtering stopwords and short tokens."""
    return [
        w for w in re.split(r'[^a-z0-9]+', text.lower())
        if len(w) > 2 and w not in STOPWORDS
    ]


def keyword_overlap(a: List[str], b: List[str]) -> float:
    """Fraction of keywords in `a` that also appear in `b`."""
    if not a or not b:
        return 0.0
    b_set = set(b)
    matches = sum(1 for w in a if w in b_set)
    return matches / len(a)


# ---------------------------------------------------------------------------
# Number / timeframe extraction
# ---------------------------------------------------------------------------

def extract_number_with_unit(text: str) -> Optional[str]:
    """Extract first number with unit (%, $, currency symbol, M/B/K suffix)."""
    m = re.search(r'[\$\u00a3\u20ac]?\d[\d,]*\.?\d*\s*[%MBKmbk]?', text)
    if m and len(m.group().strip()) >= 2:
        return m.group().strip()
    return None


def extract_timeframe(text: str) -> Optional[str]:
    """Extract timeframe phrase from lowercased text."""
    lower = text.lower()
    # "within 24 months"
    m = re.search(r'within\s+[\d]+\s+\w+', lower)
    if m:
        return m.group()
    # "by March 2027", "by 2028"
    m = re.search(r'by\s+(?:january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\s*\d*', lower)
    if m:
        return m.group()
    # "X months"
    m = re.search(r'\d+\s*months', lower)
    if m:
        return m.group()
    return None


# ---------------------------------------------------------------------------
# Prediction detection
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences (simple heuristic)."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if len(s.strip()) > 10]


def _detect_quantitative_target(sentence: str, lower: str) -> Optional[Prediction]:
    target_patterns = [
        "reduce", "increase", "achieve", "improve by", "grow by",
        "decrease", "cut by", "raise to", "target of", "goal of",
    ]
    has_target = any(p in lower for p in target_patterns)
    has_number = any(c.isdigit() for c in sentence) and (
        '%' in lower or '\u00a3' in lower or '$' in lower or '\u20ac' in lower
    )
    if has_target and has_number:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.QUANTITATIVE_TARGET,
            target_value=extract_number_with_unit(sentence),
            timeframe=extract_timeframe(sentence),
        )
    return None


def _detect_cost_estimate(sentence: str, lower: str) -> Optional[Prediction]:
    cost_patterns = ["estimated", "cost of", "budget of", "investment of", "\u00a3", "$"]
    has_cost = any(p in lower for p in cost_patterns)
    has_large = "million" in lower or "billion" in lower or '\u00a3' in lower or '$' in lower
    has_timeframe = "over" in lower or "per year" in lower or "annual" in lower
    if has_cost and has_large and has_timeframe:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.COST_ESTIMATE,
            target_value=extract_number_with_unit(sentence),
            timeframe=extract_timeframe(sentence),
        )
    return None


def _detect_timeline(sentence: str, lower: str) -> Optional[Prediction]:
    timeline_patterns = [
        "within", "by march", "by april", "by may", "by june", "by july",
        "by august", "by september", "by october", "by november", "by december",
        "by january", "by february", "by 20", "months", "phase 1", "phase 2", "phase 3",
    ]
    has_timeline = any(p in lower for p in timeline_patterns)
    has_action = any(w in lower for w in ["will", "shall", "plan to", "aim to", "deliver"])
    if has_timeline and has_action and len(sentence) > 30:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.TIMELINE,
            timeframe=extract_timeframe(sentence),
        )
    return None


def _detect_comparison(sentence: str, lower: str) -> Optional[Prediction]:
    compare_patterns = [
        "achieves", "compared to", "better than", "worse than",
        "more effective", "less effective", "outperforms", "% of the",
    ]
    has_compare = any(p in lower for p in compare_patterns)
    has_number = any(c.isdigit() for c in sentence)
    if has_compare and has_number:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.COMPARISON_CLAIM,
            target_value=extract_number_with_unit(sentence),
        )
    return None


def _detect_qualitative_goal(sentence: str, lower: str) -> Optional[Prediction]:
    goal_patterns = [
        "will improve", "will enhance", "aims to", "seeks to",
        "will ensure", "will establish", "will create", "will develop",
    ]
    has_goal = any(p in lower for p in goal_patterns)
    no_number = not any(c.isdigit() for c in sentence)
    if has_goal and no_number and len(sentence) > 25:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.QUALITATIVE_GOAL,
            timeframe=extract_timeframe(sentence),
        )
    return None


def _detect_commitment(sentence: str, lower: str) -> Optional[Prediction]:
    commit_patterns = ["we will", "we commit", "we pledge", "we guarantee", "we shall"]
    has_commit = any(p in lower for p in commit_patterns)
    if has_commit and len(sentence) > 20:
        return Prediction(
            text=sentence,
            prediction_type=PredictionType.COMMITMENT,
            timeframe=extract_timeframe(sentence),
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_predictions(text: str, section_title: str = "") -> List[Prediction]:
    """
    Extract predictions, targets, timelines, and commitments from text.

    Each sentence is checked against detection patterns (first match wins).
    """
    predictions: List[Prediction] = []
    sentences = _split_sentences(text)

    detectors = [
        _detect_quantitative_target,
        _detect_cost_estimate,
        _detect_timeline,
        _detect_comparison,
        _detect_qualitative_goal,
        _detect_commitment,
    ]

    for sentence in sentences:
        lower = sentence.lower()
        for detector in detectors:
            pred = detector(sentence, lower)
            if pred:
                pred.section_title = section_title
                predictions.append(pred)
                break

    return predictions


def assess_credibility(
    predictions: List[Prediction],
    evidence_texts: List[str],
    claim_texts: List[str] = None,
) -> List[Prediction]:
    """
    Assess credibility of each prediction based on available evidence.

    Args:
        predictions: Predictions to assess
        evidence_texts: List of evidence strings (e.g. from search results, graph data)
        claim_texts: Optional list of supporting claim strings

    Returns:
        The same predictions list with credibility fields populated
    """
    claim_texts = claim_texts or []

    # Pre-extract keywords for evidence and claims
    evidence_kw = [(et, extract_keywords(et.lower())) for et in evidence_texts]
    claim_kw = [(ct, extract_keywords(ct.lower())) for ct in claim_texts]

    for pred in predictions:
        pred_keywords = extract_keywords(pred.text.lower())
        supporting = []
        risks = []
        evidence_score = 0.0

        # Check supporting evidence
        for ev_text, ev_keys in evidence_kw:
            overlap = keyword_overlap(pred_keywords, ev_keys)
            if overlap > 0.2:
                snippet = ev_text[:80] + "..." if len(ev_text) > 80 else ev_text
                supporting.append(f"Evidence: {snippet} (relevance: {overlap*100:.0f}%)")
                # Quantified evidence gets higher weight
                has_numbers = any(c.isdigit() for c in ev_text)
                evidence_score += 0.3 if has_numbers else 0.15

        # Check supporting claims
        for cl_text, cl_keys in claim_kw:
            overlap = keyword_overlap(pred_keywords, cl_keys)
            if overlap > 0.3:
                evidence_score += 0.1

        # Risk factors by prediction type
        if pred.prediction_type == PredictionType.QUANTITATIVE_TARGET:
            if not pred.timeframe:
                risks.append("No timeframe specified -- target is open-ended")
                evidence_score *= 0.8
            if not supporting:
                risks.append("No evidence cited to support this target")
                evidence_score *= 0.5

        elif pred.prediction_type == PredictionType.COST_ESTIMATE:
            if not supporting:
                risks.append("Cost estimate not backed by evidence or breakdown")
                evidence_score *= 0.5

        elif pred.prediction_type == PredictionType.COMPARISON_CLAIM:
            if not supporting:
                risks.append("Comparison claim has no cited evidence base")
                evidence_score *= 0.4

        elif pred.prediction_type == PredictionType.QUALITATIVE_GOAL:
            risks.append("Qualitative goal -- difficult to measure achievement")
            evidence_score *= 0.7

        elif pred.prediction_type == PredictionType.COMMITMENT:
            if not supporting:
                risks.append("Commitment made without evidence of capacity to deliver")
                evidence_score *= 0.6

        elif pred.prediction_type == PredictionType.TIMELINE:
            if not supporting:
                risks.append("Timeline not supported by implementation evidence")
                evidence_score *= 0.6

        score = max(0.0, min(1.0, evidence_score))

        if score >= 0.7:
            verdict = CredibilityVerdict.WELL_SUPPORTED
        elif score >= 0.4:
            verdict = CredibilityVerdict.PARTIALLY_SUPPORTED
        elif score >= 0.15:
            verdict = CredibilityVerdict.ASPIRATIONAL
        else:
            verdict = CredibilityVerdict.UNSUPPORTED

        confidence = 0.3
        if evidence_texts:
            confidence = min(1.0, (len(supporting) / 3.0)) * 0.5 + 0.3

        verdict_desc = {
            CredibilityVerdict.WELL_SUPPORTED: "Well supported by available evidence",
            CredibilityVerdict.PARTIALLY_SUPPORTED: "Partially supported -- some evidence but gaps",
            CredibilityVerdict.ASPIRATIONAL: "Aspirational -- plausible but limited evidence",
            CredibilityVerdict.UNSUPPORTED: "Unsupported -- no evidence base found",
            CredibilityVerdict.OVER_CLAIMED: "Over-claimed -- evidence doesn't support the scale",
        }

        explanation = (
            f"{pred.prediction_type.value}: {verdict_desc[verdict]} "
            f"(credibility {score*100:.0f}%, confidence {confidence*100:.0f}%). "
            f"{len(supporting)} supporting evidence items. "
            f"{'Risk factors present.' if risks else 'No risk factors.'}"
        )

        pred.credibility = CredibilityAssessment(
            score=score,
            confidence=confidence,
            supporting_evidence=supporting,
            risk_factors=risks,
            verdict=verdict,
            explanation=explanation,
        )

    return predictions


def credibility_summary(predictions: List[Prediction]) -> str:
    """Generate a markdown summary of prediction credibility assessments."""
    if not predictions:
        return ""

    lines = [
        f"\n### Prediction Credibility Assessment\n",
        f"{len(predictions)} prediction(s)/target(s) extracted.\n",
        "| Prediction | Type | Credibility | Verdict |",
        "|---|---|---|---|",
    ]

    for pred in predictions:
        text = pred.text[:60] + "..." if len(pred.text) > 60 else pred.text
        lines.append(
            f"| {text} | {pred.prediction_type.value} | "
            f"{pred.credibility.score*100:.0f}% | {pred.credibility.verdict.value} |"
        )

    lines.append("")
    for i, pred in enumerate(predictions, 1):
        lines.append(f"**{i}. {pred.text[:80]}**\n")
        if pred.target_value:
            lines.append(f"- Target: {pred.target_value}")
        if pred.timeframe:
            lines.append(f"- Timeframe: {pred.timeframe}")
        lines.append(f"- Credibility: {pred.credibility.score*100:.0f}% ({pred.credibility.verdict.value})")
        if pred.credibility.risk_factors:
            lines.append("- Risk factors:")
            for rf in pred.credibility.risk_factors:
                lines.append(f"  - {rf}")
        lines.append("")

    return "\n".join(lines)
