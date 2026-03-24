"""Neo4j compatibility helpers for the local Graphiti-backed graph."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from neo4j import AsyncGraphDatabase

from ..config import Config
from .logger import get_logger

logger = get_logger('mirofish.zep_paging')

_GENERIC_LABELS = {"Entity", "Node"}


@dataclass
class Neo4jEntityNode:
    uuid_: str
    name: str = ""
    labels: list[str] = field(default_factory=list)
    summary: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: Any = None


@dataclass
class Neo4jEntityEdge:
    uuid_: str
    name: str = ""
    fact: str = ""
    source_node_uuid: str = ""
    target_node_uuid: str = ""
    source_node_name: str = ""
    target_node_name: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: Any = None
    valid_at: Any = None
    invalid_at: Any = None
    expired_at: Any = None
    episodes: list[str] = field(default_factory=list)


def _run_async(coro):
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


def _normalize_labels(*label_sources: Any) -> list[str]:
    labels: set[str] = set()

    for source in label_sources:
        if source is None:
            continue
        if isinstance(source, str):
            parsed = _maybe_parse_json(source)
            if isinstance(parsed, list):
                labels.update(str(item) for item in parsed if item)
            elif source:
                labels.add(source)
            continue
        if isinstance(source, (list, tuple, set)):
            labels.update(str(item) for item in source if item)

    ordered: list[str] = []
    for generic_label in ("Entity", "Node"):
        if generic_label in labels:
            ordered.append(generic_label)
            labels.discard(generic_label)

    ordered.extend(sorted(labels))
    return ordered


def _maybe_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _coerce_dict(value: Any) -> dict[str, Any]:
    value = _maybe_parse_json(value)
    if isinstance(value, dict):
        return value
    return {}


def _coerce_list(value: Any, fallback: Any = None) -> list[str]:
    candidate = _maybe_parse_json(value)
    if isinstance(candidate, (list, tuple, set)):
        return [str(item) for item in candidate if item is not None]

    fallback_candidate = _maybe_parse_json(fallback)
    if isinstance(fallback_candidate, (list, tuple, set)):
        return [str(item) for item in fallback_candidate if item is not None]

    if candidate is None:
        return []

    return [str(candidate)]


def _neo4j_driver():
    return AsyncGraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
    )


def _build_node(record: dict[str, Any]) -> Neo4jEntityNode:
    return Neo4jEntityNode(
        uuid_=str(record.get("uuid") or ""),
        name=record.get("name") or "",
        labels=_normalize_labels(record.get("neo4j_labels"), record.get("stored_labels")),
        summary=record.get("summary") or "",
        attributes=_coerce_dict(record.get("attributes")),
        created_at=record.get("created_at"),
    )


def _build_edge(record: dict[str, Any]) -> Neo4jEntityEdge:
    source_node_uuid = record.get("source_node_uuid") or record.get("source_uuid_fallback") or ""
    target_node_uuid = record.get("target_node_uuid") or record.get("target_uuid_fallback") or ""

    return Neo4jEntityEdge(
        uuid_=str(record.get("uuid") or ""),
        name=record.get("name") or "",
        fact=record.get("fact") or "",
        source_node_uuid=str(source_node_uuid),
        target_node_uuid=str(target_node_uuid),
        source_node_name=record.get("source_node_name") or "",
        target_node_name=record.get("target_node_name") or "",
        attributes=_coerce_dict(record.get("attributes")),
        created_at=record.get("created_at"),
        valid_at=record.get("valid_at"),
        invalid_at=record.get("invalid_at"),
        expired_at=record.get("expired_at"),
        episodes=_coerce_list(record.get("episodes"), fallback=record.get("episode_ids")),
    )


async def fetch_all_nodes_async(graph_id: str) -> list[Neo4jEntityNode]:
    driver = _neo4j_driver()
    try:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n:Entity {group_id: $gid})
                RETURN
                    n.uuid AS uuid,
                    n.name AS name,
                    labels(n) AS neo4j_labels,
                    n.labels AS stored_labels,
                    n.summary AS summary,
                    n.attributes AS attributes,
                    n.created_at AS created_at
                """,
                gid=graph_id,
            )
            records = [record async for record in result]
    finally:
        await driver.close()

    nodes = [_build_node(record.data()) for record in records]
    nodes.sort(key=lambda node: node.uuid_)
    return nodes


async def fetch_all_edges_async(graph_id: str) -> list[Neo4jEntityEdge]:
    driver = _neo4j_driver()
    try:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH ()-[r:RELATES_TO {group_id: $gid}]-()
                OPTIONAL MATCH (source:Entity {uuid: r.source_node_uuid, group_id: $gid})
                OPTIONAL MATCH (target:Entity {uuid: r.target_node_uuid, group_id: $gid})
                RETURN DISTINCT
                    r.uuid AS uuid,
                    r.name AS name,
                    r.fact AS fact,
                    r.source_node_uuid AS source_node_uuid,
                    r.target_node_uuid AS target_node_uuid,
                    source.uuid AS source_uuid_fallback,
                    target.uuid AS target_uuid_fallback,
                    source.name AS source_node_name,
                    target.name AS target_node_name,
                    r.attributes AS attributes,
                    r.created_at AS created_at,
                    r.valid_at AS valid_at,
                    r.invalid_at AS invalid_at,
                    r.expired_at AS expired_at,
                    r.episodes AS episodes,
                    r.episode_ids AS episode_ids
                """,
                gid=graph_id,
            )
            records = [record async for record in result]
    finally:
        await driver.close()

    edges = [_build_edge(record.data()) for record in records]
    edges.sort(key=lambda edge: edge.uuid_)
    return edges


async def delete_graph_group_async(graph_id: str) -> None:
    driver = _neo4j_driver()
    try:
        async with driver.session() as session:
            await session.run(
                """
                MATCH ()-[r {group_id: $gid}]-()
                DELETE r
                """,
                gid=graph_id,
            )
            await session.run(
                """
                MATCH (n {group_id: $gid})
                DETACH DELETE n
                """,
                gid=graph_id,
            )
    finally:
        await driver.close()


def fetch_all_nodes(graph_id: str) -> list[Neo4jEntityNode]:
    return _run_async(fetch_all_nodes_async(graph_id))


def fetch_all_edges(graph_id: str) -> list[Neo4jEntityEdge]:
    return _run_async(fetch_all_edges_async(graph_id))


def delete_graph_group(graph_id: str) -> None:
    _run_async(delete_graph_group_async(graph_id))
