"""
Quality Validator
6 validation checks for report/deliberation text quality.
Ported from brain-in-the-fish validate.rs — pure Python, no Rust dependency.
"""

import re
from enum import Enum
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger('mirofish.quality_validator')


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SignalType(str, Enum):
    EVIDENCE_QUALITY = "evidence_quality"
    LOGICAL_FALLACY = "logical_fallacy"
    HEDGING_BALANCE = "hedging_balance"
    SPECIFICITY = "specificity"
    ARGUMENT_FLOW = "argument_flow"
    COUNTER_ARGUMENT = "counter_argument"


@dataclass
class ValidationSignal:
    signal_type: SignalType
    severity: Severity
    title: str
    description: str
    impact_score: float = 0.0  # -1 to +1

    def to_dict(self) -> Dict:
        return {
            "signal_type": self.signal_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "impact_score": round(self.impact_score, 3),
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_text(
    text: str,
    sections: Optional[List[Dict]] = None,
) -> List[ValidationSignal]:
    """
    Run all applicable validation checks on the provided text.

    Args:
        text: Full text to validate
        sections: Optional list of dicts with 'title' and 'content' keys
                  (for section-aware checks like argument_flow and evidence_quality).
                  If not provided, the text is treated as a single section.

    Returns:
        List of ValidationSignal findings
    """
    signals: List[ValidationSignal] = []

    signals.extend(check_logical_fallacies(text))
    signals.extend(check_hedging_balance(text))
    signals.extend(check_specificity(text))
    signals.extend(check_counter_arguments(text))

    if sections and len(sections) >= 2:
        signals.extend(check_evidence_quality(sections))
        if len(sections) >= 3:
            signals.extend(check_argument_flow(sections))

    return signals


# ---------------------------------------------------------------------------
# Check: Evidence quality
# ---------------------------------------------------------------------------

def check_evidence_quality(sections: List[Dict]) -> List[ValidationSignal]:
    """
    Assess evidence-to-claim ratio across sections.

    Each section dict should have 'title' and 'content' keys.
    Claims are detected as assertive sentences; evidence as sentences
    containing numbers, citations, or data references.
    """
    signals: List[ValidationSignal] = []

    total_claims = 0
    total_evidence = 0
    quantified_evidence = 0

    for section in sections:
        content = section.get("content", "")
        sentences = _split_sentences(content)

        for sent in sentences:
            lower = sent.lower()
            has_data = bool(re.search(r'\d+', sent))
            has_citation = bool(re.search(r'\(\w+[,\s]+\d{4}\)', sent)) or "[" in sent
            is_evidence = has_data or has_citation

            if is_evidence:
                total_evidence += 1
                if has_data:
                    quantified_evidence += 1
            else:
                # Heuristic: sentences without data/citations are claims
                total_claims += 1

    if total_claims > 0:
        ratio = total_evidence / total_claims
        if ratio < 0.5:
            signals.append(ValidationSignal(
                signal_type=SignalType.EVIDENCE_QUALITY,
                severity=Severity.WARNING,
                title=f"Low evidence-to-claim ratio ({ratio:.1f}:1)",
                description=(
                    f"{total_claims} claims but only {total_evidence} evidence items. "
                    "Many claims are unsupported. Aim for at least 1 evidence item per claim."
                ),
                impact_score=-0.05,
            ))
        elif ratio >= 1.0:
            signals.append(ValidationSignal(
                signal_type=SignalType.EVIDENCE_QUALITY,
                severity=Severity.INFO,
                title=f"Strong evidence-to-claim ratio ({ratio:.1f}:1)",
                description=(
                    f"{total_claims} claims supported by {total_evidence} evidence items. "
                    "Good evidence base."
                ),
                impact_score=0.1,
            ))

    if total_evidence > 0:
        quant_pct = quantified_evidence / total_evidence * 100
        if quant_pct >= 50:
            signals.append(ValidationSignal(
                signal_type=SignalType.EVIDENCE_QUALITY,
                severity=Severity.INFO,
                title=f"{quant_pct:.0f}% of evidence is quantified",
                description=(
                    f"{quantified_evidence} of {total_evidence} evidence items include "
                    "quantified outcomes. This strengthens the empirical basis."
                ),
                impact_score=0.1,
            ))

    return signals


# ---------------------------------------------------------------------------
# Check: Logical fallacies
# ---------------------------------------------------------------------------

FALLACY_PATTERNS = [
    (
        "Ad hominem",
        ["they are wrong because", "critics fail to", "opponents are"],
        "Attacking the person rather than the argument weakens the reasoning.",
    ),
    (
        "Appeal to authority",
        ["experts agree", "studies show", "it is well known", "everyone knows"],
        "Unnamed authority claims lack verifiability. Name the source.",
    ),
    (
        "False dichotomy",
        ["either we", "the only option", "we must choose between", "there are only two"],
        "Presenting only two options ignores alternatives.",
    ),
    (
        "Slippery slope",
        ["inevitably", "will lead to", "slippery slope", "domino effect", "if we allow"],
        "Asserting an inevitable chain of consequences without evidence.",
    ),
    (
        "Hasty generalisation",
        ["all of them", "every single", "always without exception", "never once"],
        "Absolute claims from limited evidence are rarely defensible.",
    ),
    (
        "Straw man",
        ["some people foolishly claim", "opponents naively believe"],
        "Misrepresenting an opposing view weakens the argument.",
    ),
    (
        "Circular reasoning",
        ["this is true because it is true", "as we already proved"],
        "The conclusion restates the premise without new evidence.",
    ),
]


def check_logical_fallacies(text: str) -> List[ValidationSignal]:
    """Detect common logical fallacy markers in text."""
    signals: List[ValidationSignal] = []
    lower = text.lower()

    for fallacy_name, markers, explanation in FALLACY_PATTERNS:
        for marker in markers:
            if marker in lower:
                signals.append(ValidationSignal(
                    signal_type=SignalType.LOGICAL_FALLACY,
                    severity=Severity.WARNING,
                    title=f"Possible {fallacy_name}: '{marker}'",
                    description=f"Text contains '{marker}'. {explanation}",
                    impact_score=-0.15,
                ))

    return signals


# ---------------------------------------------------------------------------
# Check: Hedging balance
# ---------------------------------------------------------------------------

HEDGE_WORDS = [
    "might", "could", "perhaps", "possibly", "seems", "appears",
    "suggests", "may", "arguably", "potentially", "likely",
]

STRONG_WORDS = [
    "clearly", "obviously", "undoubtedly", "certainly",
    "proves", "demonstrates conclusively", "without question",
    "undeniably", "irrefutably",
]


def check_hedging_balance(text: str) -> List[ValidationSignal]:
    """Detect over-hedging or under-hedging."""
    signals: List[ValidationSignal] = []
    words = text.split()
    word_count = len(words)
    if word_count < 30:
        return signals

    lower = text.lower()
    hedge_count = sum(lower.count(h) for h in HEDGE_WORDS)
    strong_count = sum(lower.count(s) for s in STRONG_WORDS)

    hedge_pct = hedge_count / word_count * 100
    strong_pct = strong_count / word_count * 100

    if hedge_pct > 8.0:
        signals.append(ValidationSignal(
            signal_type=SignalType.HEDGING_BALANCE,
            severity=Severity.WARNING,
            title=f"Over-hedged text ({hedge_pct:.1f}% hedging)",
            description=(
                f"Text has {hedge_pct:.1f}% hedging words. "
                "Excessive hedging weakens the argument. Ideal range is 3-8%."
            ),
            impact_score=-0.1,
        ))
    elif hedge_pct < 1.0 and strong_pct > 3.0:
        signals.append(ValidationSignal(
            signal_type=SignalType.HEDGING_BALANCE,
            severity=Severity.WARNING,
            title=f"Under-hedged text ({strong_pct:.1f}% strong assertions)",
            description=(
                f"Text has many strong assertions ({strong_pct:.1f}%) but little hedging "
                f"({hedge_pct:.1f}%). This may indicate overclaiming."
            ),
            impact_score=-0.1,
        ))
    elif 3.0 <= hedge_pct <= 8.0:
        signals.append(ValidationSignal(
            signal_type=SignalType.HEDGING_BALANCE,
            severity=Severity.INFO,
            title=f"Well-balanced hedging ({hedge_pct:.1f}%)",
            description=f"Text shows appropriate hedging balance ({hedge_pct:.1f}%).",
            impact_score=0.05,
        ))

    return signals


# ---------------------------------------------------------------------------
# Check: Specificity
# ---------------------------------------------------------------------------

VAGUE_MARKERS = [
    "things", "stuff", "aspects", "various", "a number of",
    "several", "a lot of", "good", "bad", "interesting",
    "important", "significant", "nice", "great",
]


def check_specificity(text: str) -> List[ValidationSignal]:
    """Flag vague or generic language."""
    signals: List[ValidationSignal] = []
    words = text.split()
    word_count = len(words)
    if word_count < 20:
        return signals

    lower = text.lower()
    vague_count = 0
    for marker in VAGUE_MARKERS:
        # Word-boundary-aware matching
        for m in re.finditer(re.escape(marker), lower):
            pos = m.start()
            end_pos = m.end()
            before_ok = (pos == 0) or not lower[pos - 1].isalnum()
            after_ok = (end_pos >= len(lower)) or not lower[end_pos].isalnum()
            if before_ok and after_ok:
                vague_count += 1

    per_100 = vague_count / word_count * 100

    if per_100 > 5.0:
        signals.append(ValidationSignal(
            signal_type=SignalType.SPECIFICITY,
            severity=Severity.WARNING,
            title=f"High vagueness density ({per_100:.1f} per 100 words)",
            description=(
                f"Text has {per_100:.1f} vague terms per 100 words "
                f"({vague_count} in {word_count} words). "
                "Replace generic language with specific details."
            ),
            impact_score=-0.1,
        ))
    elif per_100 < 1.0 and word_count >= 50:
        signals.append(ValidationSignal(
            signal_type=SignalType.SPECIFICITY,
            severity=Severity.INFO,
            title="Specific, precise language",
            description=f"Text uses precise language with few vague terms ({per_100:.1f} per 100 words).",
            impact_score=0.05,
        ))

    return signals


# ---------------------------------------------------------------------------
# Check: Counter-arguments
# ---------------------------------------------------------------------------

COUNTER_MARKERS = [
    "however", "on the other hand", "critics argue", "alternatively",
    "despite this", "conversely", "nevertheless", "opponents suggest",
    "a counter-argument", "it could be objected", "some may argue",
    "an alternative view",
]


def check_counter_arguments(text: str) -> List[ValidationSignal]:
    """Detect engagement with opposing views."""
    signals: List[ValidationSignal] = []
    word_count = len(text.split())
    if word_count < 500:
        return signals

    lower = text.lower()
    total_counter = sum(lower.count(m) for m in COUNTER_MARKERS)

    if total_counter == 0:
        signals.append(ValidationSignal(
            signal_type=SignalType.COUNTER_ARGUMENT,
            severity=Severity.WARNING,
            title="No counter-argument engagement",
            description=(
                f"The text ({word_count} words) contains no counter-argument markers. "
                "One-sided arguments are weaker in analytical contexts."
            ),
            impact_score=-0.15,
        ))
    elif total_counter >= 3:
        signals.append(ValidationSignal(
            signal_type=SignalType.COUNTER_ARGUMENT,
            severity=Severity.INFO,
            title=f"Good counter-argument engagement ({total_counter} instances)",
            description="The text engages with opposing views, strengthening its argument.",
            impact_score=0.1,
        ))

    return signals


# ---------------------------------------------------------------------------
# Check: Argument flow
# ---------------------------------------------------------------------------

_FLOW_STOPWORDS = frozenset([
    "about", "above", "after", "again", "against", "along", "among",
    "around", "because", "before", "being", "below", "between", "beyond",
    "could", "would", "should", "these", "those", "their", "there",
    "through", "under", "until", "which", "while", "where", "other",
    "another", "every", "further", "having", "itself", "might", "since",
    "still", "than", "that", "them", "then", "this", "very", "what",
    "when", "with", "within", "without", "also", "been", "does", "from",
    "have", "here", "into", "just", "more", "most", "much", "must",
    "only", "over", "same", "some", "such", "will", "your",
])


def _content_keywords(text: str) -> Set[str]:
    """Extract significant content keywords (>4 chars, not stopwords)."""
    words = re.findall(r'[a-z]+', text.lower())
    return {w for w in words if len(w) > 4 and w not in _FLOW_STOPWORDS}


def check_argument_flow(sections: List[Dict]) -> List[ValidationSignal]:
    """
    Detect logical argument progression across sections.

    Requires at least 3 sections (intro, body, conclusion).
    Each section dict should have 'title' and 'content' keys.
    """
    signals: List[ValidationSignal] = []

    if len(sections) < 3:
        return signals

    intro_kw = _content_keywords(sections[0].get("content", ""))
    conclusion_kw = _content_keywords(sections[-1].get("content", ""))
    body_kw: Set[str] = set()
    for s in sections[1:-1]:
        body_kw.update(_content_keywords(s.get("content", "")))

    if not intro_kw or not conclusion_kw:
        return signals

    intro_body_overlap = len(intro_kw & body_kw) / max(len(intro_kw), 1)
    intro_conclusion_overlap = len(intro_kw & conclusion_kw) / max(len(intro_kw), 1)

    if intro_body_overlap < 0.2:
        signals.append(ValidationSignal(
            signal_type=SignalType.ARGUMENT_FLOW,
            severity=Severity.WARNING,
            title="Weak intro-to-body connection",
            description=(
                f"Only {intro_body_overlap*100:.0f}% of introduction keywords appear in the body. "
                "The body may not develop the themes introduced."
            ),
            impact_score=-0.1,
        ))

    if intro_conclusion_overlap < 0.2:
        signals.append(ValidationSignal(
            signal_type=SignalType.ARGUMENT_FLOW,
            severity=Severity.WARNING,
            title="Weak intro-to-conclusion connection",
            description=(
                f"Only {intro_conclusion_overlap*100:.0f}% of introduction keywords appear in the conclusion. "
                "The conclusion may not address the original objectives."
            ),
            impact_score=-0.1,
        ))

    # New concepts in conclusion
    new_in_conclusion = conclusion_kw - intro_kw - body_kw
    new_ratio = len(new_in_conclusion) / max(len(conclusion_kw), 1)

    if new_ratio > 0.5:
        signals.append(ValidationSignal(
            signal_type=SignalType.ARGUMENT_FLOW,
            severity=Severity.WARNING,
            title="Conclusion introduces new concepts",
            description=(
                f"{new_ratio*100:.0f}% of conclusion keywords do not appear in the "
                "introduction or body. A conclusion should synthesise, not introduce new material."
            ),
            impact_score=-0.1,
        ))

    if intro_body_overlap >= 0.4 and intro_conclusion_overlap >= 0.4 and new_ratio <= 0.3:
        signals.append(ValidationSignal(
            signal_type=SignalType.ARGUMENT_FLOW,
            severity=Severity.INFO,
            title="Strong argument flow",
            description=(
                "Introduction, body, and conclusion share consistent themes. "
                "The argument progresses logically."
            ),
            impact_score=0.1,
        ))

    return signals


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------

def validation_summary(signals: List[ValidationSignal]) -> str:
    """Generate a markdown summary of validation signals."""
    if not signals:
        return ""

    warnings = [s for s in signals if s.severity == Severity.WARNING]
    positives = [s for s in signals if s.severity == Severity.INFO and s.impact_score > 0]

    lines = ["\n### Quality Validation Summary\n"]

    if warnings:
        lines.append(f"**{len(warnings)} issue(s) detected:**\n")
        for s in warnings:
            lines.append(f"- **{s.title}** — {s.description}")
        lines.append("")

    if positives:
        lines.append(f"**{len(positives)} strength(s) found:**\n")
        for s in positives:
            lines.append(f"- {s.title} — {s.description}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if len(s.strip()) > 10]
