"""
News injection service
Searches for recent news related to the research topic and injects them into the simulation
"""

import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..config import Config
from ..utils.logger import get_logger
from .search_service import SearchService

logger = get_logger('mirofish.news_injection')


@dataclass
class NewsItem:
    """A news item to be injected into the simulation"""
    title: str
    content: str
    source_url: str = ""
    source_name: str = ""
    published_at: str = ""
    relevance_score: float = 0.0
    injected: bool = False
    injected_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "relevance_score": self.relevance_score,
            "injected": self.injected,
            "injected_at": self.injected_at
        }


class NewsInjectionService:
    """
    Service for injecting real-world news into simulations.
    Searches for recent news related to the research topic and formats them
    for injection into the OASIS simulation environment.
    """

    def __init__(self, search_service: Optional[SearchService] = None):
        self.search_service = search_service or SearchService()
        self._injection_log: Dict[str, List[NewsItem]] = {}
        logger.info("NewsInjectionService initialized")

    def generate_news_seeds(
        self,
        requirement: str,
        entity_types: Optional[List[str]] = None
    ) -> List[NewsItem]:
        """
        Search for recent news related to the research topic.

        Args:
            requirement: The research/simulation requirement
            entity_types: Optional list of entity types to focus on

        Returns:
            List of NewsItem objects
        """
        logger.info(f"Generating news seeds for: {requirement[:80]}...")

        # Build search queries
        queries = [
            f"latest news {requirement}",
            f"recent developments {requirement}",
        ]

        if entity_types:
            for etype in entity_types[:3]:
                queries.append(f"{etype} {requirement} news")

        # Search and collect results
        news_items = []
        seen_urls = set()

        for query in queries[:5]:
            try:
                result = self.search_service.search(
                    query=query,
                    context="Find recent news articles and developments related to this topic."
                )

                for citation in result.citations:
                    if citation.url and citation.url not in seen_urls:
                        seen_urls.add(citation.url)
                        news_items.append(NewsItem(
                            title=citation.title or "Untitled",
                            content=citation.snippet or result.answer[:500],
                            source_url=citation.url,
                            source_name=citation.title.split(" - ")[-1] if " - " in citation.title else "",
                            published_at=datetime.now().isoformat(),
                            relevance_score=0.8
                        ))

            except Exception as e:
                logger.warning(f"News search failed for query '{query}': {e}")

        logger.info(f"Generated {len(news_items)} news seeds")
        return news_items

    def format_for_simulation(self, news_items: List[NewsItem]) -> List[Dict[str, Any]]:
        """
        Convert news items into OASIS event format.

        Args:
            news_items: List of NewsItem objects

        Returns:
            List of event dicts for OASIS injection
        """
        events = []
        for item in news_items:
            content = f"[EXTERNAL_NEWS_INJECTION] {item.title}\n\n{item.content}"
            if item.source_url:
                content += f"\n\nSource: {item.source_url}"

            events.append({
                "content": content,
                "poster_type": "MediaOutlet",
                "metadata": {
                    "type": "news_injection",
                    "source_url": item.source_url,
                    "source_name": item.source_name,
                    "title": item.title,
                }
            })

        return events

    def inject_into_simulation(
        self,
        simulation_id: str,
        news_items: List[NewsItem]
    ) -> None:
        """
        Inject news items into the simulation. Tags all items with [EXTERNAL_NEWS_INJECTION].

        Args:
            simulation_id: Simulation ID
            news_items: List of NewsItem to inject
        """
        logger.info(f"Injecting {len(news_items)} news items into simulation {simulation_id}")

        for item in news_items:
            item.injected = True
            item.injected_at = datetime.now().isoformat()

        # Store injection log
        if simulation_id not in self._injection_log:
            self._injection_log[simulation_id] = []
        self._injection_log[simulation_id].extend(news_items)

        logger.info(f"News injection complete for simulation {simulation_id}")

    def get_injection_log(self, simulation_id: str) -> List[NewsItem]:
        """
        Get the injection log for a simulation.

        Args:
            simulation_id: Simulation ID

        Returns:
            List of injected NewsItem objects
        """
        return self._injection_log.get(simulation_id, [])
