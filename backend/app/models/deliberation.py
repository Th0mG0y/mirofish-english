"""
Deliberation data models
Data classes for adversarial council debates, voting, and synthesis
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.llm_provider import Citation


class DeliberationStatus(str, Enum):
    """Deliberation session status"""
    CREATED = "created"
    DEBATING = "debating"
    VOTING = "voting"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CouncilMember:
    """A member of the optimist or pessimist council"""
    member_id: str
    name: str
    role: str  # 'optimist' or 'pessimist'
    persona_prompt: str
    tier: str = ""  # info tier / expertise area

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "name": self.name,
            "role": self.role,
            "persona_prompt": self.persona_prompt,
            "tier": self.tier
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CouncilMember":
        return cls(
            member_id=data.get("member_id", ""),
            name=data.get("name", ""),
            role=data.get("role", ""),
            persona_prompt=data.get("persona_prompt", ""),
            tier=data.get("tier", "")
        )


@dataclass
class Argument:
    """An argument made by a council member during debate"""
    member_id: str
    round_number: int
    position: str  # 'optimist' or 'pessimist'
    content: str
    evidence: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    confidence: float = 0.0
    credibility_score: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "round_number": self.round_number,
            "position": self.position,
            "content": self.content,
            "evidence": self.evidence,
            "citations": [
                {"url": c.url, "title": c.title, "snippet": c.snippet}
                for c in self.citations
            ],
            "confidence": self.confidence,
            "credibility_score": self.credibility_score,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Argument":
        citations = [
            Citation(url=c.get("url", ""), title=c.get("title", ""), snippet=c.get("snippet", ""))
            for c in data.get("citations", [])
        ]
        return cls(
            member_id=data.get("member_id", ""),
            round_number=data.get("round_number", 0),
            position=data.get("position", ""),
            content=data.get("content", ""),
            evidence=data.get("evidence", []),
            citations=citations,
            confidence=data.get("confidence", 0.0),
            credibility_score=data.get("credibility_score"),
            timestamp=data.get("timestamp", "")
        )


@dataclass
class DeliberationRound:
    """A single round of debate"""
    round_number: int
    arguments: List[Argument] = field(default_factory=list)
    expert_testimonies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "arguments": [a.to_dict() for a in self.arguments],
            "expert_testimonies": self.expert_testimonies
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliberationRound":
        return cls(
            round_number=data.get("round_number", 0),
            arguments=[Argument.from_dict(a) for a in data.get("arguments", [])],
            expert_testimonies=data.get("expert_testimonies", [])
        )


@dataclass
class VoteDimension:
    """A dimension along which agents vote"""
    name: str
    description: str
    position_a_label: str
    position_b_label: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "position_a_label": self.position_a_label,
            "position_b_label": self.position_b_label
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoteDimension":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            position_a_label=data.get("position_a_label", ""),
            position_b_label=data.get("position_b_label", "")
        )


@dataclass
class Vote:
    """A single agent's vote on a dimension"""
    agent_id: str
    dimension: str
    choice: str  # 'position_a', 'position_b', or 'neither'
    confidence_stake: int  # 1-10
    justification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "dimension": self.dimension,
            "choice": self.choice,
            "confidence_stake": self.confidence_stake,
            "justification": self.justification
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Vote":
        return cls(
            agent_id=data.get("agent_id", ""),
            dimension=data.get("dimension", ""),
            choice=data.get("choice", ""),
            confidence_stake=data.get("confidence_stake", 5),
            justification=data.get("justification", "")
        )


@dataclass
class DeliberationSession:
    """Full deliberation session state"""
    session_id: str
    simulation_id: str
    graph_id: str
    topic: str
    status: DeliberationStatus = DeliberationStatus.CREATED

    optimist_council: List[CouncilMember] = field(default_factory=list)
    pessimist_council: List[CouncilMember] = field(default_factory=list)
    rounds: List[DeliberationRound] = field(default_factory=list)

    vote_dimensions: List[VoteDimension] = field(default_factory=list)
    votes: List[Vote] = field(default_factory=list)
    vote_results: Dict[str, Any] = field(default_factory=dict)

    synthesis: Optional[str] = None
    sentinel_alerts: List[Dict[str, Any]] = field(default_factory=list)
    quality_signals: Optional[List[Dict[str, Any]]] = None

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "topic": self.topic,
            "status": self.status.value,
            "optimist_council": [m.to_dict() for m in self.optimist_council],
            "pessimist_council": [m.to_dict() for m in self.pessimist_council],
            "rounds": [r.to_dict() for r in self.rounds],
            "vote_dimensions": [d.to_dict() for d in self.vote_dimensions],
            "votes": [v.to_dict() for v in self.votes],
            "vote_results": self.vote_results,
            "synthesis": self.synthesis,
            "sentinel_alerts": self.sentinel_alerts,
            "quality_signals": self.quality_signals,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliberationSession":
        return cls(
            session_id=data.get("session_id", ""),
            simulation_id=data.get("simulation_id", ""),
            graph_id=data.get("graph_id", ""),
            topic=data.get("topic", ""),
            status=DeliberationStatus(data.get("status", "created")),
            optimist_council=[CouncilMember.from_dict(m) for m in data.get("optimist_council", [])],
            pessimist_council=[CouncilMember.from_dict(m) for m in data.get("pessimist_council", [])],
            rounds=[DeliberationRound.from_dict(r) for r in data.get("rounds", [])],
            vote_dimensions=[VoteDimension.from_dict(d) for d in data.get("vote_dimensions", [])],
            votes=[Vote.from_dict(v) for v in data.get("votes", [])],
            vote_results=data.get("vote_results", {}),
            synthesis=data.get("synthesis"),
            sentinel_alerts=data.get("sentinel_alerts", []),
            quality_signals=data.get("quality_signals"),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at")
        )
