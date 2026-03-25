"""
Source quality and freshness heuristics for web search results.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set
from urllib.parse import urlparse

from ..utils.llm_provider import Citation


OFFICIAL_DOMAINS = (
    ".gov",
    ".gouv",
    ".europa.eu",
    ".who.int",
    ".sec.gov",
)
REPUTABLE_HINTS = (
    "reuters",
    "apnews",
    "ft.com",
    "wsj.com",
    "bloomberg",
    "oecd",
    "worldbank",
    "mckinsey",
    "gartner",
)

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "over", "will",
    "what", "when", "where", "why", "how", "does", "have", "has", "had", "within",
    "after", "before", "about", "their", "there", "which", "would", "could", "should",
    "your", "than", "then", "them", "they", "were", "been", "being", "against", "across",
    "under", "between", "through", "because", "while", "market", "report", "analysis",
    "current", "latest", "state", "benchmarks", "metrics", "adoption", "pricing",
    "question", "strongest", "evidence", "based", "answer",
}


@dataclass
class RankedSource:
    citation: Citation
    score: float
    source_type: str
    freshness: str
    relevance: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "url": self.citation.url,
            "title": self.citation.title,
            "snippet": self.citation.snippet,
            "score": round(self.score, 3),
            "source_type": self.source_type,
            "freshness": self.freshness,
            "relevance": self.relevance,
        }


class SourceQualityRanker:
    def rank_sources(self, citations: List[Citation], topic: str = "") -> List[RankedSource]:
        ranked = [self._rank_source(citation, topic) for citation in citations]
        return sorted(ranked, key=lambda item: item.score, reverse=True)

    def summarize(self, citations: List[Citation], topic: str = "") -> Dict[str, object]:
        ranked = self.rank_sources(citations, topic)
        if not ranked:
            return {
                "count": 0,
                "relevant_count": 0,
                "off_topic_count": 0,
                "best_source_type": "none",
                "freshness": "unknown",
                "independent_domains": 0,
            }

        relevant = [item for item in ranked if item.relevance != "off_topic"]
        domains = {
            urlparse(item.citation.url).netloc.lower()
            for item in relevant
            if item.citation.url
        }
        return {
            "count": len(ranked),
            "relevant_count": len(relevant),
            "off_topic_count": len(ranked) - len(relevant),
            "best_source_type": (relevant[0].source_type if relevant else ranked[0].source_type),
            "freshness": (relevant[0].freshness if relevant else ranked[0].freshness),
            "independent_domains": len(domains),
            "top_sources": [item.to_dict() for item in (relevant[:3] or ranked[:3])],
        }

    def _rank_source(self, citation: Citation, topic: str) -> RankedSource:
        url = (citation.url or "").lower()
        title = (citation.title or "").lower()
        snippet = (citation.snippet or "").lower()
        domain = urlparse(url).netloc.lower()
        source_text = " ".join([title, snippet, domain.replace(".", " "), url.replace("/", " ")])
        topic_tokens = self._topic_tokens(topic)
        source_tokens = self._text_tokens(source_text)
        topic_bigrams = self._bigrams(topic_tokens)
        phrase_overlap = sum(1 for phrase in topic_bigrams if phrase in source_text)
        anchor_tokens = self._anchor_tokens(topic_tokens)
        anchor_overlap = anchor_tokens & source_tokens
        overlap = topic_tokens & source_tokens

        score = 0.25
        source_type = "secondary"
        if any(url.endswith(suffix) or suffix in domain for suffix in OFFICIAL_DOMAINS):
            score += 0.45
            source_type = "official"
        elif any(hint in domain for hint in REPUTABLE_HINTS):
            score += 0.3
            source_type = "reputable_reporting"
        elif any(token in domain for token in ["investor", "ir.", "company", "corp", "inc", "llc"]):
            score += 0.2
            source_type = "company_disclosure"

        if topic_tokens:
            score += min(0.22, len(anchor_overlap) * 0.08 + phrase_overlap * 0.07 + len(overlap) * 0.025)

        freshness = self._freshness_from_text(" ".join([title, snippet, url]))
        if freshness == "fresh":
            score += 0.15
        elif freshness == "recent":
            score += 0.1
        elif freshness == "stale":
            score -= 0.05

        relevance = self._classify_relevance(topic_tokens, source_tokens, overlap, anchor_overlap, phrase_overlap)
        if relevance == "direct":
            score += 0.15
        elif relevance == "supporting":
            score += 0.03
        else:
            score -= 0.3

        return RankedSource(
            citation=citation,
            score=max(0.0, min(score, 1.0)),
            source_type=source_type,
            freshness=freshness,
            relevance=relevance,
        )

    def _classify_relevance(
        self,
        topic_tokens: Set[str],
        source_tokens: Set[str],
        overlap: Set[str],
        anchor_overlap: Set[str],
        phrase_overlap: int,
    ) -> str:
        if not topic_tokens or not source_tokens:
            return "supporting"
        if phrase_overlap > 0 or len(anchor_overlap) >= 2:
            return "direct"
        if len(anchor_overlap) >= 1 and (len(topic_tokens) <= 6 or len(overlap) >= 2):
            return "supporting"
        if len(overlap) >= 3:
            return "supporting"
        return "off_topic"

    def _topic_tokens(self, topic: str) -> Set[str]:
        return {
            token
            for token in self._text_tokens(topic)
            if token not in STOPWORDS
        }

    def _anchor_tokens(self, tokens: Set[str]) -> Set[str]:
        return {
            token for token in tokens
            if len(token) >= 4 and token not in STOPWORDS
        }

    def _text_tokens(self, text: str) -> Set[str]:
        return {
            token
            for token in re.split(r"[^a-z0-9]+", text.lower())
            if len(token) >= 2
        }

    def _bigrams(self, tokens: Set[str]) -> Set[str]:
        ordered = sorted(tokens)
        return {
            f"{ordered[index]} {ordered[index + 1]}"
            for index in range(len(ordered) - 1)
        }

    def _freshness_from_text(self, text: str) -> str:
        years = [int(match) for match in re.findall(r"\b(20\d{2})\b", text)]
        if not years:
            return "unknown"

        current_year = datetime.now(timezone.utc).year
        newest = max(years)
        age = current_year - newest
        if age <= 1:
            return "fresh"
        if age <= 3:
            return "recent"
        return "stale"
