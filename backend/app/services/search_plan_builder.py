"""
Build structured search plans for report runs.
"""

import re
from typing import Dict, List, Set
from uuid import uuid4

from .report_artifacts import ReportIntentArtifact, SearchPlanQuery
from ..utils.llm_client import LLMClient

SEARCH_PLAN_SYSTEM_PROMPT = """\
You create non-overlapping web search tasks from source chunks.

Rules:
- Each task must come from a specific chunk.
- Do not use canned search patterns or generic query templates.
- Derive each query directly from the chunk text.
- Queries should be concise and search-engine-ready.
- Each task should either search for more evidence or verify information already present in the chunk.
- Avoid overlap across tasks. If two chunks would lead to the same search, keep only the stronger one.
- Stay domain-agnostic, brand-agnostic, and industry-agnostic.

Return JSON with this shape:
{
  "tasks": [
    {
      "chunk_id": "chunk identifier",
      "query": "search query derived from the chunk",
      "mode": "search" or "verify",
      "task": "short explanation of what this search is trying to establish",
      "focus_terms": ["term1", "term2"]
    }
  ]
}"""


class SearchPlanBuilder:
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def build(self, intent: ReportIntentArtifact, source_material: List[Dict[str, str]] = None) -> List[SearchPlanQuery]:
        source_material = source_material or []
        chunks = self._normalize_chunks(intent, source_material)
        raw_tasks = self._generate_tasks(intent, chunks)
        tasks: List[SearchPlanQuery] = []
        seen_focuses: List[Set[str]] = []
        seen_queries: Set[str] = set()
        chunk_lookup = {chunk["id"]: chunk for chunk in chunks}

        for item in raw_tasks:
            chunk = chunk_lookup.get(item.get("chunk_id", ""))
            if not chunk:
                continue

            query = " ".join((item.get("query") or "").split()).strip()
            if not query:
                continue
            normalized_query = query.lower()
            if normalized_query in seen_queries:
                continue

            focus_terms = [
                token.lower()
                for token in item.get("focus_terms", [])
                if isinstance(token, str) and token.strip()
            ] or self._query_terms(query)
            if not focus_terms:
                continue
            if self._is_overlapping(focus_terms, seen_focuses):
                continue

            mode = str(item.get("mode", "search")).strip().lower()
            intent_name = "verify" if mode == "verify" else "search"

            tasks.append(
                SearchPlanQuery(
                    query=query,
                    reason=" ".join((item.get("task") or "").split()).strip(),
                    report_question=intent.main_question,
                    evidence_type="external_verification" if intent_name == "verify" else "external_search",
                    intent=intent_name,
                    chunk_id=chunk["id"],
                    chunk_label=chunk["label"],
                    source_chunk=chunk["text"][:700],
                    focus_terms=focus_terms[:10],
                    overlap_key=" ".join(sorted(set(focus_terms[:6]))),
                )
            )
            seen_queries.add(normalized_query)
            seen_focuses.append(set(focus_terms))

            if len(tasks) >= 8:
                break

        return tasks[:8]

    def _normalize_chunks(self, intent: ReportIntentArtifact, source_material: List[Dict[str, str]]) -> List[Dict[str, str]]:
        normalized = []
        for index, item in enumerate(source_material):
            label = (item.get("label") or f"chunk_{index + 1}").strip().lower()
            text = " ".join((item.get("text") or "").split()).strip()
            if len(text) < 30:
                continue
            normalized.append({
                "id": item.get("id") or f"{label}_{index + 1}",
                "label": label,
                "text": text,
            })

        if not normalized:
            fallback = " ".join((intent.main_question or "").split())
            normalized.append({"id": "question_1", "label": "question", "text": fallback or "report topic"})

        return normalized

    def _generate_tasks(self, intent: ReportIntentArtifact, chunks: List[Dict[str, str]]) -> List[Dict[str, object]]:
        chunk_payload = [
            {
                "chunk_id": chunk["id"],
                "chunk_label": chunk["label"],
                "chunk_text": chunk["text"][:900],
            }
            for chunk in chunks[:8]
        ]
        prompt = (
            f"Main question:\n{intent.main_question}\n\n"
            f"Time horizon:\n{intent.time_horizon}\n\n"
            f"Recency-sensitive topics:\n{', '.join(intent.recency_sensitive_topics) or 'none'}\n\n"
            f"Source chunks:\n{chunk_payload}\n"
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": SEARCH_PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1800,
            )
            tasks = response.get("tasks", [])
            if isinstance(tasks, list):
                return tasks
        except Exception:
            pass

        fallback_tasks = []
        for chunk in chunks[:8]:
            query = self._fallback_query(chunk["text"])
            if not query:
                continue
            fallback_tasks.append(
                {
                    "chunk_id": chunk["id"],
                    "query": query,
                    "mode": "search",
                    "task": "",
                    "focus_terms": self._query_terms(query),
                    "task_id": str(uuid4()),
                }
            )
        return fallback_tasks

    def _is_overlapping(self, focus_terms: List[str], seen_focuses: List[Set[str]]) -> bool:
        focus_set = set(focus_terms)
        for prior in seen_focuses:
            overlap = len(focus_set & prior)
            union = len(focus_set | prior)
            if union and overlap / union >= 0.6:
                return True
        return False

    def _fallback_query(self, text: str) -> str:
        terms = self._query_terms(text)
        return " ".join(terms[:8])

    def _query_terms(self, text: str) -> List[str]:
        terms = []
        for token in re.split(r"[^a-zA-Z0-9]+", text):
            cleaned = token.strip().lower()
            if len(cleaned) < 3:
                continue
            if cleaned in terms:
                continue
            terms.append(cleaned)
        return terms[:12]
