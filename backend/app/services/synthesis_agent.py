"""
Synthesis Agent
Produces synthesis when voting reveals contested dimensions or "neither" positions
"""

import json
import re
from typing import Optional, Dict, Any

from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..models.deliberation import DeliberationSession

logger = get_logger('mirofish.synthesis_agent')


class SynthesisAgent:
    """
    Synthesizes deliberation outcomes into coherent analysis.
    Triggered when "neither" exceeds threshold on any dimension, or when dimensions are contested.
    """

    def synthesize(
        self,
        session: DeliberationSession,
        vote_results: Dict[str, Any],
        llm_client: Optional[LLMClient] = None
    ) -> str:
        """
        Produce a synthesis addressing each voted dimension.

        Args:
            session: The completed deliberation session
            vote_results: Aggregated vote results
            llm_client: LLM client

        Returns:
            Synthesis text (markdown)
        """
        client = llm_client or LLMClient()

        # Build debate context
        debate_context = self._build_debate_context(session)
        vote_context = self._format_vote_results(vote_results)

        contested = vote_results.get("contested_dimensions", [])
        neither_triggered = vote_results.get("neither_triggered", [])

        prompt = f"""You are a synthesis analyst. The following adversarial debate has concluded and agents have voted.

**Topic:** {session.topic}

**Debate Summary:**
{debate_context[:4000]}

**Voting Results:**
{vote_context}

**Contested Dimensions (40-60% split):** {', '.join(contested) if contested else 'None'}
**Neither Threshold Triggered (>20%):** {', '.join(neither_triggered) if neither_triggered else 'None'}

Your task:
1. For each dimension, synthesize the strongest points from both sides
2. For contested dimensions, explain WHY reasonable minds differ and what additional information could resolve the disagreement
3. For "neither" triggered dimensions, articulate the OFF-AXIS position that voters were reaching for — the position that neither council fully captured
4. Include a confidence assessment for each synthesis point
5. Reference specific arguments and evidence from both councils

Write a structured synthesis in markdown format with sections for each dimension."""

        try:
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert synthesis analyst who produces balanced, nuanced analysis from adversarial debates. Write in clear, professional English."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=3000
            )

            synthesis = response.get("content", "")
            logger.info(f"Synthesis generated: {len(synthesis)} chars")
            return synthesis

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"Synthesis generation failed: {str(e)}"

    def generate_executive_summary(
        self,
        session: DeliberationSession,
        llm_client: Optional[LLMClient] = None
    ) -> str:
        """
        Generate a concise executive summary of the entire deliberation.

        Args:
            session: The completed deliberation session
            llm_client: LLM client

        Returns:
            Executive summary text
        """
        client = llm_client or LLMClient()

        debate_context = self._build_debate_context(session)
        vote_context = self._format_vote_results(session.vote_results)

        prompt = f"""Write a concise executive summary (3-5 paragraphs) of this deliberation.

Topic: {session.topic}

Debate (abbreviated):
{debate_context[:3000]}

Voting Results:
{vote_context}

Synthesis:
{session.synthesis[:2000] if session.synthesis else 'Not available'}

The summary should:
- State the topic and key question
- Summarize the strongest arguments from each side
- Present the voting outcome
- Highlight key areas of agreement and disagreement
- State the overall conclusion with appropriate caveats"""

        try:
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": "Write clear, concise executive summaries suitable for inclusion in analytical reports."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )

            summary = response.get("content", "")
            logger.info(f"Executive summary generated: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Executive summary failed: {e}")
            return f"Executive summary generation failed: {str(e)}"

    def _build_debate_context(self, session: DeliberationSession) -> str:
        """Build a text representation of the debate."""
        parts = []
        for rnd in session.rounds:
            parts.append(f"### Round {rnd.round_number}")
            for arg in rnd.arguments:
                label = "OPTIMIST" if arg.position == "optimist" else "PESSIMIST"
                parts.append(f"**[{label} — {arg.member_id}]** (confidence: {arg.confidence:.0%})")
                parts.append(arg.content[:500])
                if arg.evidence:
                    parts.append("Evidence: " + "; ".join(arg.evidence[:3]))
                parts.append("")
        return "\n".join(parts)

    def _format_vote_results(self, vote_results: Dict[str, Any]) -> str:
        """Format vote results as readable text."""
        if not vote_results:
            return "No voting results available."

        parts = []
        for dim_name, dim_data in vote_results.get("dimensions", {}).items():
            parts.append(f"**{dim_name}**")
            parts.append(f"  Position A ({dim_data.get('position_a_label', 'A')}): {dim_data.get('raw_percentage', {}).get('position_a', 0)}%")
            parts.append(f"  Position B ({dim_data.get('position_b_label', 'B')}): {dim_data.get('raw_percentage', {}).get('position_b', 0)}%")
            parts.append(f"  Neither: {dim_data.get('raw_percentage', {}).get('neither', 0)}%")
            parts.append(f"  Confidence-weighted: A={dim_data.get('confidence_weighted', {}).get('position_a', 0)}%, B={dim_data.get('confidence_weighted', {}).get('position_b', 0)}%")
            parts.append("")

        contested = vote_results.get("contested_dimensions", [])
        if contested:
            parts.append(f"Contested dimensions: {', '.join(contested)}")

        neither = vote_results.get("neither_triggered", [])
        if neither:
            parts.append(f"Neither threshold triggered: {', '.join(neither)}")

        return "\n".join(parts)
