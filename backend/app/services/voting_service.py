"""
Voting Service
Multi-dimensional blind voting with confidence-weighted aggregation
"""

import json
import re
from difflib import get_close_matches
from typing import Optional, List, Dict, Any

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..models.deliberation import (
    DeliberationSession, VoteDimension, Vote
)

logger = get_logger('mirofish.voting_service')


class VotingService:
    """
    Conducts multi-dimensional blind voting on deliberation outcomes.
    Agents vote on LLM-generated dimensions with confidence stakes.
    """

    def generate_vote_dimensions(
        self,
        session: DeliberationSession,
        llm_client: Optional[LLMClient] = None
    ) -> List[VoteDimension]:
        """
        Generate voting dimensions from the debate content.

        Args:
            session: The deliberation session with completed debate rounds
            llm_client: LLM client for generation

        Returns:
            List of VoteDimension objects
        """
        client = llm_client or LLMClient()

        # Summarize the debate
        debate_summary = self._summarize_debate(session)

        prompt = f"""Based on the following adversarial debate, identify 3-5 key dimensions where the two sides disagree.

For each dimension, provide BLIND labels (Position A vs Position B) that do NOT reveal which council proposed which position.

Debate summary:
{debate_summary[:4000]}

Return JSON:
{{
    "dimensions": [
        {{
            "name": "Dimension name",
            "description": "What this dimension measures",
            "position_a_label": "Position A description (neutral label)",
            "position_b_label": "Position B description (neutral label)"
        }}
    ]
}}"""

        try:
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You analyze debates and identify key dimensions of disagreement. Use neutral, blind labels. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            content = response.get("content", "")
            content = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.IGNORECASE)
            content = re.sub(r'\n?```\s*$', '', content)
            data = json.loads(content.strip())

            dimensions = []
            for d in data.get("dimensions", [])[:5]:
                dimensions.append(VoteDimension(
                    name=d.get("name", ""),
                    description=d.get("description", ""),
                    position_a_label=d.get("position_a_label", "Position A"),
                    position_b_label=d.get("position_b_label", "Position B")
                ))

            logger.info(f"Generated {len(dimensions)} vote dimensions")
            return dimensions

        except Exception as e:
            logger.error(f"Failed to generate vote dimensions: {e}")
            return [VoteDimension(
                name="Overall Assessment",
                description="Which overall position is more compelling?",
                position_a_label="The optimistic outlook is more likely",
                position_b_label="The pessimistic outlook is more likely"
            )]

    def conduct_voting(
        self,
        session: DeliberationSession,
        agent_profiles: List[Dict[str, Any]],
        llm_client: Optional[LLMClient] = None
    ) -> List[Vote]:
        """
        Conduct voting across all agents and dimensions.

        Args:
            session: The deliberation session
            agent_profiles: List of agent profile dicts (from simulation)
            llm_client: LLM client

        Returns:
            List of Vote objects
        """
        client = llm_client or LLMClient()
        debate_summary = self._summarize_debate(session)
        votes = []

        # Format dimensions for the voting prompt
        dim_text = ""
        for i, dim in enumerate(session.vote_dimensions):
            dim_text += f"\nDimension {i+1}: {dim.name}\n"
            dim_text += f"  Description: {dim.description}\n"
            dim_text += f"  Position A: {dim.position_a_label}\n"
            dim_text += f"  Position B: {dim.position_b_label}\n"

        dimension_names = [dim.name for dim in session.vote_dimensions]

        # Generate votes for each agent
        for agent in agent_profiles[:20]:  # Cap at 20 agents
            agent_id = str(agent.get("agent_id", agent.get("id", "")))
            agent_name = agent.get("name", agent.get("agent_name", f"Agent {agent_id}"))
            agent_bio = agent.get("bio", agent.get("description", ""))

            prompt = f"""You are {agent_name}. {agent_bio}

You have observed the following debate between two analytical councils:

{debate_summary[:3000]}

Now vote on each dimension. For each, choose position_a, position_b, or neither, and assign a confidence stake (1-10, where 10 = absolute certainty).

You must keep the dimension reference aligned with the list above.
Return `dimension_index` using the number shown above, and copy the `dimension` name exactly as written.

Dimensions:{dim_text}

Return JSON:
{{
    "votes": [
        {{
            "dimension_index": 1,
            "dimension": "dimension name",
            "choice": "position_a" or "position_b" or "neither",
            "confidence_stake": 1-10,
            "justification": "brief reason"
        }}
    ]
}}"""

            try:
                response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": f"You are {agent_name}, voting based on your perspective. Return valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                )

                content = response.get("content", "")
                content = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.IGNORECASE)
                content = re.sub(r'\n?```\s*$', '', content)
                vote_data = json.loads(content.strip())

                for v in vote_data.get("votes", []):
                    resolved_dimension = self._resolve_dimension_name(
                        raw_dimension=v.get("dimension", ""),
                        dimensions=session.vote_dimensions,
                        dimension_names=dimension_names,
                        dimension_index=v.get("dimension_index"),
                    )

                    if not resolved_dimension:
                        logger.warning(
                            "Skipping vote from agent %s because the dimension could not be matched: %s",
                            agent_id,
                            v.get("dimension", ""),
                        )
                        continue

                    votes.append(Vote(
                        agent_id=agent_id,
                        dimension=resolved_dimension,
                        choice=self._normalize_choice(v.get("choice", "neither")),
                        confidence_stake=min(10, max(1, int(v.get("confidence_stake", 5)))),
                        justification=v.get("justification", "")
                    ))

            except Exception as e:
                logger.warning(f"Failed to get votes from agent {agent_id}: {e}")

        logger.info(f"Voting complete: {len(votes)} votes from {len(agent_profiles)} agents")
        return votes

    def _resolve_dimension_name(
        self,
        raw_dimension: Any,
        dimensions: List[VoteDimension],
        dimension_names: List[str],
        dimension_index: Any = None,
    ) -> Optional[str]:
        if isinstance(dimension_index, str) and dimension_index.isdigit():
            dimension_index = int(dimension_index)

        if isinstance(dimension_index, int) and 1 <= dimension_index <= len(dimensions):
            return dimensions[dimension_index - 1].name

        if not raw_dimension:
            return None

        raw_dimension_text = str(raw_dimension).strip()
        if not raw_dimension_text:
            return None

        normalized_lookup = {
            self._normalize_dimension_key(dim.name): dim.name
            for dim in dimensions
        }

        exact_match = normalized_lookup.get(self._normalize_dimension_key(raw_dimension_text))
        if exact_match:
            return exact_match

        for dim in dimensions:
            if raw_dimension_text.lower() == dim.name.lower():
                return dim.name
            if raw_dimension_text.lower() == dim.position_a_label.lower():
                return dim.name
            if raw_dimension_text.lower() == dim.position_b_label.lower():
                return dim.name

        if raw_dimension_text.lower().startswith("dimension "):
            suffix = raw_dimension_text.split(" ", 1)[1].strip()
            if suffix.isdigit():
                suffix_index = int(suffix)
                if 1 <= suffix_index <= len(dimensions):
                    return dimensions[suffix_index - 1].name

        close_matches = get_close_matches(
            self._normalize_dimension_key(raw_dimension_text),
            list(normalized_lookup.keys()),
            n=1,
            cutoff=0.72,
        )
        if close_matches:
            return normalized_lookup[close_matches[0]]

        return None

    def _normalize_choice(self, raw_choice: Any) -> str:
        normalized = str(raw_choice or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "a": "position_a",
            "positiona": "position_a",
            "option_a": "position_a",
            "b": "position_b",
            "positionb": "position_b",
            "option_b": "position_b",
            "abstain": "neither",
            "neutral": "neither",
        }
        if normalized in {"position_a", "position_b", "neither"}:
            return normalized
        return aliases.get(normalized, "neither")

    def _normalize_dimension_key(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', value.lower())

    def aggregate_results(self, votes: List[Vote], dimensions: List[VoteDimension]) -> Dict[str, Any]:
        """
        Aggregate voting results with confidence weighting.

        Returns:
            Dict with per-dimension results and overall analysis
        """
        dim_names = {d.name for d in dimensions}
        results = {"dimensions": {}, "contested_dimensions": [], "neither_triggered": []}

        for dim in dimensions:
            dim_votes = [v for v in votes if v.dimension == dim.name]
            if not dim_votes:
                continue

            raw = {"position_a": 0, "position_b": 0, "neither": 0}
            weighted = {"position_a": 0.0, "position_b": 0.0, "neither": 0.0}
            confidence_sums = {"position_a": [], "position_b": [], "neither": []}

            for v in dim_votes:
                choice = v.choice if v.choice in raw else "neither"
                raw[choice] += 1
                weighted[choice] += v.confidence_stake
                confidence_sums[choice].append(v.confidence_stake)

            total = sum(raw.values()) or 1
            total_weighted = sum(weighted.values()) or 1.0

            raw_pct = {k: round(v / total * 100, 1) for k, v in raw.items()}
            weighted_pct = {k: round(v / total_weighted * 100, 1) for k, v in weighted.items()}
            mean_conf = {
                k: round(sum(vals) / len(vals), 1) if vals else 0.0
                for k, vals in confidence_sums.items()
            }

            results["dimensions"][dim.name] = {
                "raw_count": raw,
                "raw_percentage": raw_pct,
                "confidence_weighted": weighted_pct,
                "mean_confidence": mean_conf,
                "total_votes": total,
                "position_a_label": dim.position_a_label,
                "position_b_label": dim.position_b_label
            }

            # Check if contested (40-60% zone)
            min_pct = min(raw_pct["position_a"], raw_pct["position_b"])
            if min_pct >= 40.0:
                results["contested_dimensions"].append(dim.name)

            # Check if neither threshold exceeded
            if raw_pct["neither"] > 20.0:
                results["neither_triggered"].append(dim.name)

        return results

    def detect_contested(self, results: Dict[str, Any], threshold: float = 0.4) -> List[str]:
        """Returns dimension names where vote split is within contested zone."""
        return results.get("contested_dimensions", [])

    def _summarize_debate(self, session: DeliberationSession) -> str:
        """Create a text summary of the debate for use in prompts."""
        parts = []
        for rnd in session.rounds:
            parts.append(f"--- Round {rnd.round_number} ---")
            for arg in rnd.arguments:
                parts.append(f"[{arg.position.upper()} - {arg.member_id}]")
                parts.append(arg.content[:600])
                parts.append("")
        return "\n".join(parts)
