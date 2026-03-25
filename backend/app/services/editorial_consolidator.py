"""
Editorial review and deduplication helpers.
"""

import re
from typing import Dict, List, Tuple

from .report_artifacts import EditorialDefectArtifact


class EditorialConsolidator:
    def review(self, sections: List[Dict[str, str]]) -> List[EditorialDefectArtifact]:
        defects: List[EditorialDefectArtifact] = []
        seen_sentences: Dict[str, List[str]] = {}

        for section in sections:
            title = section.get("title", "")
            content = section.get("content", "")

            if self._has_format_artifacts(content):
                defects.append(
                    EditorialDefectArtifact(
                        defect_type="formatting_artifact",
                        severity="warning",
                        description=f"Section '{title}' still contains broken markdown or raw note artifacts.",
                        section=title,
                    )
                )

            if self._looks_truncated(content):
                defects.append(
                    EditorialDefectArtifact(
                        defect_type="truncated_section",
                        severity="warning",
                        description=f"Section '{title}' appears truncated or ends mid-thought.",
                        section=title,
                    )
                )

            if len(content.split()) < 50 and title not in {"Run Trace", "Quantitative Checks"}:
                defects.append(
                    EditorialDefectArtifact(
                        defect_type="shallow_section",
                        severity="warning",
                        description=f"Section '{title}' may be too shallow for decision use.",
                        section=title,
                    )
                )

            if "[UNVERIFIED" in content and "What Is Inferred" not in title:
                defects.append(
                    EditorialDefectArtifact(
                        defect_type="unlabeled_uncertainty",
                        severity="warning",
                        description="Simulation-derived or unresolved claims remain in a primary section.",
                        section=title,
                    )
                )

            for sentence in self._sentences(content):
                normalized = self._normalize(sentence)
                if len(normalized) < 24:
                    continue
                seen_sentences.setdefault(normalized, []).append(title)

        normalized_items = list(seen_sentences.items())
        for sentence, titles in normalized_items:
            if len(set(titles)) > 1:
                defects.append(
                    EditorialDefectArtifact(
                        defect_type="repetition",
                        severity="warning",
                        description=f"Repeated talking point appears across sections: {sentence[:120]}",
                        section=", ".join(sorted(set(titles))),
                    )
                )

        for idx, (sentence, titles) in enumerate(normalized_items):
            for other_sentence, other_titles in normalized_items[idx + 1:]:
                if self._similarity(sentence, other_sentence) >= 0.58 and set(titles) != set(other_titles):
                    defects.append(
                        EditorialDefectArtifact(
                            defect_type="repetition_cluster",
                            severity="warning",
                            description=(
                                "Multiple sections restate the same underlying fact with slightly different wording: "
                                f"{sentence[:80]}"
                            ),
                            section=", ".join(sorted(set([*titles, *other_titles]))),
                        )
                    )
                    break

        return defects

    def deduplicate_sections(self, sections: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[EditorialDefectArtifact]]:
        cleaned_sections = [
            {
                **section,
                "content": self.clean_section_content(section.get("title", ""), section.get("content", "")),
            }
            for section in sections
        ]
        defects = self.review(cleaned_sections)
        updated = []
        global_seen = []

        for section in cleaned_sections:
            content = section.get("content", "")
            kept = []
            for sentence in self._sentences(content):
                normalized = self._normalize(sentence)
                if len(normalized) > 24 and any(self._similarity(normalized, seen) >= 0.58 for seen in global_seen):
                    continue
                global_seen.append(normalized)
                kept.append(sentence)
            updated.append({
                **section,
                "content": " ".join(kept).strip() or content,
            })

        return updated, defects

    def clean_section_content(self, title: str, content: str) -> str:
        if not content:
            return ""

        cleaned_lines = []
        section_title = (title or "").strip().lower()
        for raw_line in content.replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue
            if line in {"*", "**", "***", "-", "--", "__"}:
                continue
            normalized_heading = re.sub(r"^#+\s*", "", line).strip().lower()
            if section_title and normalized_heading == section_title:
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines).strip()

        if cleaned.count("**") % 2 == 1:
            cleaned = cleaned.replace("**", "")

        if self._looks_truncated(cleaned):
            parts = [line for line in cleaned.split("\n") if line.strip()]
            if parts and len(parts[-1]) < 48:
                parts = parts[:-1]
            cleaned = "\n".join(parts).strip()

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def _sentences(self, text: str) -> List[str]:
        return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]

    def _normalize(self, text: str) -> str:
        return " ".join(re.split(r"[^a-z0-9]+", text.lower())).strip()

    def _similarity(self, left: str, right: str) -> float:
        left_tokens = {token for token in left.split() if len(token) > 2}
        right_tokens = {token for token in right.split() if len(token) > 2}
        if not left_tokens or not right_tokens:
            return 0.0
        if left_tokens <= right_tokens or right_tokens <= left_tokens:
            return 1.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / max(union, 1)

    def _has_format_artifacts(self, text: str) -> bool:
        stripped_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if any(line in {"*", "**", "***", "-", "--", "__"} for line in stripped_lines):
            return True
        if text.count("**") % 2 == 1:
            return True
        return False

    def _looks_truncated(self, text: str) -> bool:
        stripped_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not stripped_lines:
            return False
        last_line = stripped_lines[-1]
        if last_line.endswith((".", "!", "?", ":", ";", "%", "\"", "'", ")", "]")):
            return False
        if re.fullmatch(r"[\W_]+", last_line):
            return True
        prior_text = " ".join(stripped_lines[:-1])
        suspicious_tail = last_line.lower().endswith(
            (" isn", " aren", " doesn", " didn", " won", " can", " n", " aspir")
        )
        if suspicious_tail and len(last_line) < 48:
            return True
        if not prior_text and len(last_line) < 32:
            return True
        return bool(prior_text) and len(last_line) < 48
