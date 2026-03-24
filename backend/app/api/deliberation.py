"""
Deliberation API routes
Provides endpoints for adversarial council debates, voting, and synthesis
"""

import os
import json
import traceback
import threading
from flask import request, jsonify

from . import deliberation_bp
from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..models.deliberation import DeliberationSession, DeliberationStatus
from ..models.deliberation_manager import DeliberationManager
from ..services.council_engine import CouncilEngine
from ..services.voting_service import VotingService
from ..services.synthesis_agent import SynthesisAgent
from ..services.search_service import SearchService
from ..services.zep_tools import ZepToolsService

logger = get_logger('mirofish.api.deliberation')


@deliberation_bp.route('/create', methods=['POST'])
def create_deliberation():
    """
    Create a new deliberation session

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",
            "graph_id": "graph_xxxx",
            "topic": "The debate topic / research question",
            "config": { "members_per_side": 3 }  // optional
        }

    Returns:
        {
            "success": true,
            "data": { "session_id": "delib_xxxx", ... }
        }
    """
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        graph_id = data.get('graph_id')
        topic = data.get('topic')
        config = data.get('config', {})

        if not simulation_id or not graph_id or not topic:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id, graph_id, and topic"
            }), 400

        engine = CouncilEngine()
        session = engine.create_session(
            topic=topic,
            simulation_id=simulation_id,
            graph_id=graph_id,
            config=config
        )

        DeliberationManager.create(session)

        return jsonify({
            "success": True,
            "data": session.to_dict()
        })

    except Exception as e:
        logger.error(f"Failed to create deliberation: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@deliberation_bp.route('/<session_id>/run-debate', methods=['POST'])
def run_debate(session_id: str):
    """
    Run the structured debate (all rounds)

    Request (JSON):
        {
            "rounds": 3  // optional, default 3
        }
    """
    try:
        data = request.get_json() or {}
        num_rounds = data.get('rounds', 3)

        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        if session.status not in [DeliberationStatus.CREATED, DeliberationStatus.FAILED, DeliberationStatus.DEBATING]:
            return jsonify({
                "success": False,
                "error": f"Session is not in a state to run debate: {session.status.value}"
            }), 400

        # Clear any partial results from a previous failed attempt
        if session.status in [DeliberationStatus.FAILED, DeliberationStatus.DEBATING]:
            session.rounds = []

        # Persist DEBATING status immediately so duplicate requests are rejected
        session.status = DeliberationStatus.DEBATING
        DeliberationManager.update(session)

        # Run debate synchronously (can be made async if needed)
        engine = CouncilEngine()
        session = engine.run_structured_debate(session, num_rounds=num_rounds)

        DeliberationManager.update(session)

        return jsonify({
            "success": True,
            "data": session.to_dict()
        })

    except Exception as e:
        logger.error(f"Debate failed: {e}")
        # Mark session as failed
        session = DeliberationManager.get(session_id)
        if session:
            session.status = DeliberationStatus.FAILED
            DeliberationManager.update(session)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@deliberation_bp.route('/<session_id>/status', methods=['GET'])
def get_status(session_id: str):
    """Get current deliberation status and progress"""
    try:
        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        return jsonify({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "status": session.status.value,
                "rounds_completed": len(session.rounds),
                "has_votes": len(session.votes) > 0,
                "has_synthesis": session.synthesis is not None,
                "created_at": session.created_at,
                "completed_at": session.completed_at
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@deliberation_bp.route('/<session_id>/vote', methods=['POST'])
def conduct_voting(session_id: str):
    """
    Conduct multi-dimensional voting

    Request (JSON):
        {
            "dimensions": "auto"  // optional, "auto" generates dimensions from debate
        }
    """
    try:
        data = request.get_json() or {}

        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        if not session.rounds:
            return jsonify({"success": False, "error": "No debate rounds found. Run debate first."}), 400

        session.status = DeliberationStatus.VOTING
        llm_client = LLMClient()
        voting_service = VotingService()

        # Generate vote dimensions
        dimensions = voting_service.generate_vote_dimensions(session, llm_client)
        session.vote_dimensions = dimensions

        # Load agent profiles from simulation config
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            '../../uploads/simulations',
            session.simulation_id
        )
        config_path = os.path.join(sim_dir, "simulation_config.json")
        agent_profiles = []

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                sim_config = json.load(f)
            agent_profiles = sim_config.get("agent_configs", [])

        if not agent_profiles:
            # Fallback: create minimal agent profiles for voting
            agent_profiles = [{"agent_id": i, "name": f"Agent {i}"} for i in range(5)]

        # Conduct voting
        votes = voting_service.conduct_voting(session, agent_profiles, llm_client)
        session.votes = votes

        # Aggregate results
        vote_results = voting_service.aggregate_results(votes, dimensions)
        session.vote_results = vote_results

        DeliberationManager.update(session)

        return jsonify({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "dimensions": [d.to_dict() for d in dimensions],
                "vote_results": vote_results,
                "total_votes": len(votes)
            }
        })

    except Exception as e:
        logger.error(f"Voting failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@deliberation_bp.route('/<session_id>/synthesize', methods=['POST'])
def synthesize(session_id: str):
    """Trigger synthesis agent"""
    try:
        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        if not session.vote_results:
            return jsonify({"success": False, "error": "No vote results found. Run voting first."}), 400

        session.status = DeliberationStatus.SYNTHESIZING
        agent = SynthesisAgent()
        llm_client = LLMClient()

        synthesis = agent.synthesize(session, session.vote_results, llm_client)
        session.synthesis = synthesis
        session.status = DeliberationStatus.COMPLETED
        session.completed_at = __import__('datetime').datetime.now().isoformat()

        DeliberationManager.update(session)

        return jsonify({
            "success": True,
            "data": {
                "session_id": session.session_id,
                "synthesis": synthesis,
                "status": session.status.value
            }
        })

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@deliberation_bp.route('/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """Get full session data"""
    try:
        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        return jsonify({
            "success": True,
            "data": session.to_dict()
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@deliberation_bp.route('/<session_id>/trace', methods=['GET'])
def get_trace(session_id: str):
    """Get deliberation trace (who said what, vote changes)"""
    try:
        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        trace = []

        # Add debate arguments
        for rnd in session.rounds:
            for arg in rnd.arguments:
                trace.append({
                    "type": "argument",
                    "round": rnd.round_number,
                    "member_id": arg.member_id,
                    "position": arg.position,
                    "content": arg.content,
                    "confidence": arg.confidence,
                    "timestamp": arg.timestamp
                })

        # Add votes
        for vote in session.votes:
            trace.append({
                "type": "vote",
                "agent_id": vote.agent_id,
                "dimension": vote.dimension,
                "choice": vote.choice,
                "confidence_stake": vote.confidence_stake,
                "justification": vote.justification
            })

        return jsonify({
            "success": True,
            "data": {
                "session_id": session_id,
                "trace": trace,
                "total_events": len(trace)
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@deliberation_bp.route('/<session_id>/quality', methods=['GET'])
def get_quality(session_id: str):
    """
    Get quality assessment for a deliberation session.

    Returns validation signals, credibility scores for arguments,
    and overall quality metrics.
    """
    try:
        session = DeliberationManager.get(session_id)
        if not session:
            return jsonify({"success": False, "error": f"Session not found: {session_id}"}), 404

        from ..services.quality_validator import validate_text, validation_summary
        from ..services.credibility_assessor import (
            extract_predictions, assess_credibility, credibility_summary
        )

        # Collect all argument text for validation
        all_text = ""
        evidence_texts = []
        argument_credibility = []

        for rnd in session.rounds:
            for arg in rnd.arguments:
                all_text += arg.content + "\n\n"
                evidence_texts.extend(arg.evidence)
                if arg.credibility_score is not None:
                    argument_credibility.append({
                        "member_id": arg.member_id,
                        "round": arg.round_number,
                        "position": arg.position,
                        "credibility_score": arg.credibility_score,
                    })

        # Run validation checks on combined text
        signals = validate_text(all_text)

        # Extract and assess predictions from synthesis if available
        predictions = []
        if session.synthesis:
            predictions = extract_predictions(session.synthesis)
            if predictions:
                assess_credibility(predictions, evidence_texts)

        # Store quality signals on session
        session.quality_signals = [s.to_dict() for s in signals]
        DeliberationManager.update(session)

        return jsonify({
            "success": True,
            "data": {
                "session_id": session_id,
                "validation_signals": [s.to_dict() for s in signals],
                "argument_credibility": argument_credibility,
                "predictions": [p.to_dict() for p in predictions],
                "summary": {
                    "total_signals": len(signals),
                    "warnings": sum(1 for s in signals if s.severity.value == "warning"),
                    "positives": sum(1 for s in signals if s.impact_score > 0),
                    "avg_credibility": (
                        sum(a["credibility_score"] for a in argument_credibility) / len(argument_credibility)
                        if argument_credibility else None
                    ),
                }
            }
        })

    except Exception as e:
        logger.error(f"Quality assessment failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@deliberation_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_by_simulation(simulation_id: str):
    """Get deliberation session for a simulation"""
    try:
        session = DeliberationManager.get_by_simulation(simulation_id)
        if not session:
            return jsonify({
                "success": False,
                "error": f"No deliberation found for simulation: {simulation_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": session.to_dict()
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
