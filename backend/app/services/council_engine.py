"""
Council Engine
Orchestrates adversarial council debates between optimist and pessimist councils
"""

import json
import re
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..models.deliberation import (
    CouncilMember, Argument, DeliberationRound, DeliberationSession,
    DeliberationStatus
)
from .search_service import SearchService
from .zep_tools import ZepToolsService
from .credibility_assessor import extract_predictions, assess_credibility

logger = get_logger('mirofish.council_engine')


class CouncilEngine:
    """
    Orchestrates adversarial council debates.
    Generates optimist and pessimist council members, runs structured debate rounds,
    and produces arguments grounded in simulation data and web search.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        search_service: Optional[SearchService] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        self.llm_client = llm_client or LLMClient()
        self.search_service = search_service or SearchService()
        self.zep_tools = zep_tools or ZepToolsService()
        logger.info("CouncilEngine initialized")

    def create_session(
        self,
        topic: str,
        simulation_id: str,
        graph_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> DeliberationSession:
        """
        Create a new deliberation session with generated council members.

        Args:
            topic: The debate topic / simulation requirement
            simulation_id: Associated simulation ID
            graph_id: Zep graph ID for context retrieval
            config: Optional configuration overrides

        Returns:
            DeliberationSession with councils populated
        """
        config = config or {}
        members_per_side = config.get("members_per_side", 3)

        session_id = f"delib_{uuid.uuid4().hex[:12]}"
        session = DeliberationSession(
            session_id=session_id,
            simulation_id=simulation_id,
            graph_id=graph_id,
            topic=topic,
            status=DeliberationStatus.CREATED
        )

        # Generate council members via LLM
        prompt = f"""Generate {members_per_side} council members for EACH side of an adversarial debate.

Topic: {topic}

For the OPTIMIST council, create members who will argue the most positive, bullish case.
For the PESSIMIST council, create members who will argue the most negative, bearish case.

Each member should have a distinct expertise area and perspective.

Return JSON:
{{
    "optimists": [
        {{"name": "...", "expertise": "...", "persona": "A brief persona description defining their perspective and argument style"}}
    ],
    "pessimists": [
        {{"name": "...", "expertise": "...", "persona": "..."}}
    ]
}}"""

        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You generate diverse expert personas for structured debates. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            content = response.get("content", "")
            content = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.IGNORECASE)
            content = re.sub(r'\n?```\s*$', '', content)
            members_data = json.loads(content.strip())

            for i, m in enumerate(members_data.get("optimists", [])[:members_per_side]):
                session.optimist_council.append(CouncilMember(
                    member_id=f"opt_{i}",
                    name=m.get("name", f"Optimist {i+1}"),
                    role="optimist",
                    persona_prompt=m.get("persona", ""),
                    tier=m.get("expertise", "")
                ))

            for i, m in enumerate(members_data.get("pessimists", [])[:members_per_side]):
                session.pessimist_council.append(CouncilMember(
                    member_id=f"pes_{i}",
                    name=m.get("name", f"Pessimist {i+1}"),
                    role="pessimist",
                    persona_prompt=m.get("persona", ""),
                    tier=m.get("expertise", "")
                ))

        except Exception as e:
            logger.error(f"Failed to generate council members: {e}")
            # Fallback: create generic members
            for i in range(members_per_side):
                session.optimist_council.append(CouncilMember(
                    member_id=f"opt_{i}",
                    name=f"Optimist Analyst {i+1}",
                    role="optimist",
                    persona_prompt="You always find the most positive, bullish interpretation of evidence.",
                    tier="general"
                ))
                session.pessimist_council.append(CouncilMember(
                    member_id=f"pes_{i}",
                    name=f"Pessimist Analyst {i+1}",
                    role="pessimist",
                    persona_prompt="You always find the most negative, bearish interpretation of evidence.",
                    tier="general"
                ))

        logger.info(f"Session created: {session_id}, optimists={len(session.optimist_council)}, pessimists={len(session.pessimist_council)}")
        return session

    def run_round(self, session: DeliberationSession, round_num: int) -> DeliberationRound:
        """
        Run a single debate round.

        Args:
            session: The deliberation session
            round_num: Round number (1-based)

        Returns:
            DeliberationRound with arguments from both sides
        """
        logger.info(f"Running debate round {round_num} for session {session.session_id}")

        debate_round = DeliberationRound(round_number=round_num)

        # Gather context from Zep graph
        graph_context = ""
        try:
            result = self.zep_tools.quick_search(
                graph_id=session.graph_id,
                query=session.topic,
                limit=15
            )
            graph_context = result.to_text()
        except Exception as e:
            logger.warning(f"Failed to get graph context: {e}")

        # Gather web search context
        search_context = ""
        try:
            search_result = self.search_service.search(
                query=session.topic,
                context="Find recent analysis and expert opinions."
            )
            search_context = search_result.answer
        except Exception as e:
            logger.warning(f"Failed to get web search context: {e}")

        # Collect prior arguments for rebuttal
        prior_arguments = []
        for prev_round in session.rounds:
            for arg in prev_round.arguments:
                prior_arguments.append({
                    "round": prev_round.round_number,
                    "member": arg.member_id,
                    "position": arg.position,
                    "content": arg.content[:500],
                    "credibility_score": arg.credibility_score,
                })

        # Generate arguments: optimists first, then pessimists
        for member in session.optimist_council:
            arg = self._generate_argument(
                member, session.topic, prior_arguments,
                graph_context, search_context, round_num
            )
            debate_round.arguments.append(arg)

        for member in session.pessimist_council:
            arg = self._generate_argument(
                member, session.topic, prior_arguments,
                graph_context, search_context, round_num
            )
            debate_round.arguments.append(arg)

        # Assess credibility of each argument's claims
        self._assess_argument_credibility(debate_round, graph_context, search_context)

        logger.info(f"Round {round_num} complete: {len(debate_round.arguments)} arguments")
        return debate_round

    def _generate_argument(
        self,
        member: CouncilMember,
        topic: str,
        prior_arguments: List[Dict],
        graph_context: str,
        search_context: str,
        round_num: int
    ) -> Argument:
        """Generate a single argument from a council member."""

        role_instruction = (
            "Your mandate is to find the STRONGEST BULL CASE. Present the most optimistic, positive interpretation of all evidence."
            if member.role == "optimist" else
            "Your mandate is to find the STRONGEST BEAR CASE. Present the most pessimistic, negative interpretation of all evidence."
        )

        prior_text = ""
        if prior_arguments:
            prior_text = "\n\nPrior arguments from the debate:\n"
            for pa in prior_arguments[-10:]:
                cred = pa.get('credibility_score')
                cred_tag = f" [credibility: {cred:.0%}]" if cred is not None else ""
                prior_text += f"- [{pa['position'].upper()}]{cred_tag} {pa['content'][:300]}\n"

        prompt = f"""You are {member.name}, a {member.role} council member.
Expertise: {member.tier}
Persona: {member.persona_prompt}

{role_instruction}

Topic: {topic}

Round {round_num} {'(Opening arguments)' if round_num == 1 else '(Rebuttal round — address opposing arguments)'}

Research data context:
{graph_context[:3000] if graph_context else 'No graph data available.'}

Real-world context:
{search_context[:2000] if search_context else 'No web search data available.'}
{prior_text}

Provide your argument as JSON:
{{
    "content": "Your detailed argument (2-4 paragraphs)",
    "evidence": ["key evidence point 1", "key evidence point 2", ...],
    "confidence": 0.0 to 1.0
}}"""

        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": f"You are {member.name}, an expert {member.role} debater. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=4096,
                response_format={"type": "json_object"}
            )

            content = response.get("content", "")
            content = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.IGNORECASE)
            content = re.sub(r'\n?```\s*$', '', content)
            arg_data = json.loads(content.strip())

            return Argument(
                member_id=member.member_id,
                round_number=round_num,
                position=member.role,
                content=arg_data.get("content", ""),
                evidence=arg_data.get("evidence", []),
                confidence=float(arg_data.get("confidence", 0.5))
            )

        except Exception as e:
            logger.error(f"Failed to generate argument for {member.name}: {e}")
            return Argument(
                member_id=member.member_id,
                round_number=round_num,
                position=member.role,
                content=f"[Argument generation failed: {str(e)}]",
                confidence=0.0
            )

    def _assess_argument_credibility(
        self,
        debate_round: DeliberationRound,
        graph_context: str,
        search_context: str,
    ):
        """Assess credibility of each argument's claims using evidence from context."""
        evidence_texts = []
        if graph_context:
            evidence_texts.extend(
                line.strip() for line in graph_context.split('\n')
                if line.strip() and len(line.strip()) > 20
            )
        if search_context:
            evidence_texts.extend(
                line.strip() for line in search_context.split('\n')
                if line.strip() and len(line.strip()) > 20
            )

        for arg in debate_round.arguments:
            try:
                predictions = extract_predictions(arg.content)
                if predictions:
                    assess_credibility(predictions, evidence_texts, arg.evidence)
                    avg_score = sum(p.credibility.score for p in predictions) / len(predictions)
                    arg.credibility_score = round(avg_score, 3)
            except Exception as e:
                logger.warning(f"Credibility assessment failed for {arg.member_id}: {e}")

    def run_structured_debate(
        self,
        session: DeliberationSession,
        num_rounds: int = 3
    ) -> DeliberationSession:
        """
        Orchestrate a full structured debate across multiple rounds.

        Args:
            session: The deliberation session
            num_rounds: Number of debate rounds

        Returns:
            Updated DeliberationSession
        """
        session.status = DeliberationStatus.DEBATING
        logger.info(f"Starting structured debate: {session.session_id}, {num_rounds} rounds")

        for round_num in range(1, num_rounds + 1):
            debate_round = self.run_round(session, round_num)
            session.rounds.append(debate_round)

        logger.info(f"Structured debate complete: {session.session_id}")
        return session
