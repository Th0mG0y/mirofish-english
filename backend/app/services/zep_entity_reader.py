"""
Zep entity reading and filtering service
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from neo4j import AsyncGraphDatabase

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_edges, fetch_all_nodes

logger = get_logger('mirofish.zep_entity_reader')

_GENERIC_LABELS = {"Entity", "Node"}


@dataclass
class EntityNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        for label in self.labels:
            if label not in _GENERIC_LABELS:
                return label
        return None


@dataclass
class FilteredEntities:
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    def _neo4j_driver(self):
        return AsyncGraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        )

    def _node_to_dict(self, node) -> Dict[str, Any]:
        return {
            "uuid": node.uuid_,
            "name": node.name or "",
            "labels": node.labels or [],
            "summary": node.summary or "",
            "attributes": node.attributes or {},
        }

    def _edge_to_dict(self, edge) -> Dict[str, Any]:
        return {
            "uuid": edge.uuid_,
            "name": edge.name or "",
            "fact": edge.fact or "",
            "source_node_uuid": edge.source_node_uuid,
            "target_node_uuid": edge.target_node_uuid,
            "attributes": edge.attributes or {},
        }

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"Fetching all nodes for graph {graph_id}...")
        nodes = [self._node_to_dict(node) for node in fetch_all_nodes(graph_id)]
        logger.info(f"Total {len(nodes)} nodes fetched")
        return nodes

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"Fetching all edges for graph {graph_id}...")
        edges = [self._edge_to_dict(edge) for edge in fetch_all_edges(graph_id)]
        logger.info(f"Total {len(edges)} edges fetched")
        return edges

    async def _get_node_edges_async(self, node_uuid: str) -> List[Dict[str, Any]]:
        driver = self._neo4j_driver()
        try:
            async with driver.session() as session:
                group_result = await session.run(
                    """
                    MATCH (n:Entity {uuid: $node_uuid})
                    RETURN n.group_id AS group_id
                    LIMIT 1
                    """,
                    node_uuid=node_uuid,
                )
                group_record = await group_result.single()
                if not group_record or not group_record.get("group_id"):
                    return []

                result = await session.run(
                    """
                    MATCH ()-[r:RELATES_TO {group_id: $gid}]-()
                    WHERE r.source_node_uuid = $node_uuid OR r.target_node_uuid = $node_uuid
                    RETURN DISTINCT
                        r.uuid AS uuid,
                        r.name AS name,
                        r.fact AS fact,
                        r.source_node_uuid AS source_node_uuid,
                        r.target_node_uuid AS target_node_uuid,
                        r.attributes AS attributes
                    """,
                    gid=group_record["group_id"],
                    node_uuid=node_uuid,
                )
                return [record.data() async for record in result]
        finally:
            await driver.close()

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        try:
            return self._run_async(self._get_node_edges_async(node_uuid))
        except Exception as e:
            logger.warning(f"Failed to get edges for node {node_uuid}: {str(e)}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        logger.info(f"Starting to filter entities from graph {graph_id}...")

        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {node["uuid"]: node for node in all_nodes}
        entity_types_found: Set[str] = set()
        filtered_entities: List[EntityNode] = []

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [label for label in labels if label not in _GENERIC_LABELS]

            if custom_labels:
                if defined_entity_types:
                    matching_labels = [label for label in custom_labels if label in defined_entity_types]
                    if not matching_labels:
                        continue
                    entity_type = matching_labels[0]
                else:
                    entity_type = custom_labels[0]
            else:
                # Graphiti nodes may only have the generic "Entity" label;
                # treat them as valid entities with type "Entity"
                if defined_entity_types and "Entity" not in defined_entity_types:
                    continue
                entity_type = "Entity"

            entity_types_found.add(entity_type)
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges: List[Dict[str, Any]] = []
                related_node_uuids: set[str] = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges
                entity.related_nodes = [
                    {
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    }
                    for related_uuid in sorted(related_node_uuids)
                    if (related_node := node_map.get(related_uuid))
                ]

            filtered_entities.append(entity)

        logger.info(
            f"Filtering complete: total nodes {len(all_nodes)}, matching {len(filtered_entities)}, "
            f"entity types: {entity_types_found}"
        )

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=len(all_nodes),
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        try:
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {node["uuid"]: node for node in all_nodes}
            node = node_map.get(entity_uuid)
            if not node:
                return None

            edges = self.get_node_edges(entity_uuid)
            related_edges: List[Dict[str, Any]] = []
            related_node_uuids: set[str] = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            related_nodes = [
                {
                    "uuid": related_node["uuid"],
                    "name": related_node["name"],
                    "labels": related_node["labels"],
                    "summary": related_node.get("summary", ""),
                }
                for related_uuid in sorted(related_node_uuids)
                if (related_node := node_map.get(related_uuid))
            ]

            return EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=node["labels"],
                summary=node["summary"],
                attributes=node["attributes"],
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
        except Exception as e:
            logger.error(f"Failed to get entity {entity_uuid}: {str(e)}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        return self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        ).entities


