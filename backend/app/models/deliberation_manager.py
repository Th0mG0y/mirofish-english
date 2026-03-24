"""
Deliberation persistence manager
Stores deliberation sessions as JSON files on disk
"""

import os
import json
from typing import Optional, List, Dict, Any

from ..utils.logger import get_logger
from .deliberation import DeliberationSession

logger = get_logger('mirofish.deliberation_manager')


class DeliberationManager:
    """Manages deliberation session persistence using JSON files"""

    STORAGE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/deliberations'
    )

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(cls.STORAGE_DIR, exist_ok=True)

    @classmethod
    def _session_path(cls, session_id: str) -> str:
        return os.path.join(cls.STORAGE_DIR, f"{session_id}.json")

    @classmethod
    def create(cls, session: DeliberationSession) -> str:
        """Save a new session and return the session_id"""
        cls._ensure_dir()
        path = cls._session_path(session.session_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"Deliberation session created: {session.session_id}")
        return session.session_id

    @classmethod
    def get(cls, session_id: str) -> Optional[DeliberationSession]:
        """Load a session by ID"""
        path = cls._session_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return DeliberationSession.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load deliberation session {session_id}: {e}")
            return None

    @classmethod
    def update(cls, session: DeliberationSession) -> None:
        """Update an existing session"""
        cls._ensure_dir()
        path = cls._session_path(session.session_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        """List all sessions (summary info only)"""
        cls._ensure_dir()
        sessions = []
        for filename in os.listdir(cls.STORAGE_DIR):
            if not filename.endswith('.json'):
                continue
            try:
                path = os.path.join(cls.STORAGE_DIR, filename)
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "simulation_id": data.get("simulation_id"),
                    "topic": data.get("topic"),
                    "status": data.get("status"),
                    "created_at": data.get("created_at"),
                    "completed_at": data.get("completed_at"),
                    "rounds_count": len(data.get("rounds", [])),
                    "votes_count": len(data.get("votes", []))
                })
            except Exception as e:
                logger.warning(f"Failed to read deliberation file {filename}: {e}")
        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions

    @classmethod
    def delete(cls, session_id: str) -> bool:
        """Delete a session"""
        path = cls._session_path(session_id)
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Deliberation session deleted: {session_id}")
            return True
        return False

    @classmethod
    def get_by_simulation(cls, simulation_id: str) -> Optional[DeliberationSession]:
        """Get the deliberation session for a given simulation"""
        cls._ensure_dir()
        for filename in os.listdir(cls.STORAGE_DIR):
            if not filename.endswith('.json'):
                continue
            try:
                path = os.path.join(cls.STORAGE_DIR, filename)
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get("simulation_id") == simulation_id:
                    return DeliberationSession.from_dict(data)
            except Exception:
                continue
        return None
