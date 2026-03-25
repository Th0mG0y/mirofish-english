import json

from app.models.deliberation import DeliberationRound, DeliberationSession, VoteDimension
from app.services.voting_service import VotingService


class FakeVotingLLMClient:
    def __init__(self, vote_payloads):
        self._vote_payloads = list(vote_payloads)

    def chat_completion(self, **kwargs):
        return {"content": json.dumps(self._vote_payloads.pop(0))}


def build_session():
    return DeliberationSession(
        session_id="delib_1",
        simulation_id="sim_1",
        graph_id="graph_1",
        topic="Assess adoption risk",
        rounds=[DeliberationRound(round_number=1, arguments=[])],
        vote_dimensions=[
            VoteDimension(
                name="Commercial Viability",
                description="Likelihood of reaching sustainable demand",
                position_a_label="Strong commercial upside",
                position_b_label="Weak commercial upside",
            ),
            VoteDimension(
                name="Consumer Trust and Safety",
                description="Trust implications of the rollout",
                position_a_label="Trust remains intact",
                position_b_label="Trust deteriorates",
            ),
        ],
    )


def test_conduct_voting_maps_dimension_variants_back_to_canonical_names():
    service = VotingService()
    session = build_session()
    llm_client = FakeVotingLLMClient(
        [
            {
                "votes": [
                    {
                        "dimension_index": 1,
                        "dimension": "Dimension 1",
                        "choice": "A",
                        "confidence_stake": 8,
                        "justification": "Commercial upside looks durable.",
                    },
                    {
                        "dimension": "Consumer trust / safety",
                        "choice": "position b",
                        "confidence_stake": 7,
                        "justification": "Trust is fragile in this scenario.",
                    },
                ]
            }
        ]
    )

    votes = service.conduct_voting(
        session=session,
        agent_profiles=[{"agent_id": "agent_1", "name": "Agent 1"}],
        llm_client=llm_client,
    )

    assert [vote.dimension for vote in votes] == [
        "Commercial Viability",
        "Consumer Trust and Safety",
    ]
    assert [vote.choice for vote in votes] == ["position_a", "position_b"]


def test_aggregate_results_populates_dimensions_after_dimension_mapping():
    service = VotingService()
    session = build_session()
    llm_client = FakeVotingLLMClient(
        [
            {
                "votes": [
                    {
                        "dimension_index": 1,
                        "dimension": "Dimension 1",
                        "choice": "position_a",
                        "confidence_stake": 9,
                    },
                    {
                        "dimension_index": 2,
                        "dimension": "Consumer trust / safety",
                        "choice": "neither",
                        "confidence_stake": 5,
                    },
                ]
            },
            {
                "votes": [
                    {
                        "dimension": "Commercial viability",
                        "choice": "position_b",
                        "confidence_stake": 6,
                    },
                    {
                        "dimension_index": 2,
                        "dimension": "Dimension 2",
                        "choice": "position_b",
                        "confidence_stake": 7,
                    },
                ]
            },
        ]
    )

    votes = service.conduct_voting(
        session=session,
        agent_profiles=[
            {"agent_id": "agent_1", "name": "Agent 1"},
            {"agent_id": "agent_2", "name": "Agent 2"},
        ],
        llm_client=llm_client,
    )
    results = service.aggregate_results(votes, session.vote_dimensions)

    assert results["dimensions"]["Commercial Viability"]["total_votes"] == 2
    assert results["dimensions"]["Consumer Trust and Safety"]["total_votes"] == 2
    assert results["dimensions"]["Consumer Trust and Safety"]["raw_percentage"]["neither"] == 50.0
