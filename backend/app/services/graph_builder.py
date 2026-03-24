"""
Graph building service
Interface 2: Build Standalone Graph using Graphiti + Neo4j
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.graphiti_clients import (
    create_graphiti_embedder,
    create_graphiti_llm_client,
    create_graphiti_reranker,
)
from ..utils.zep_paging import (
    delete_graph_group,
    fetch_all_edges,
    fetch_all_edges_async,
    fetch_all_nodes,
    fetch_all_nodes_async,
)
from .text_processor import TextProcessor

_GENERIC_LABELS = {"Entity", "Node"}


@dataclass
class GraphInfo:
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self._build_graph_async_impl(
                    task_id,
                    text,
                    ontology,
                    graph_name,
                    chunk_size,
                    chunk_overlap,
                    batch_size,
                )
            )
        except Exception as e:
            import traceback
            self.task_manager.fail_task(task_id, f"{str(e)}\n{traceback.format_exc()}")
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    async def _build_graph_async_impl(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ) -> None:
        graphiti = None
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting graph build..."
            )

            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )

            graphiti = self._create_graphiti()
            self.task_manager.update_task(
                task_id,
                progress=11,
                message="Creating graph database indexes (first run can be slow)..."
            )
            await graphiti.build_indices_and_constraints()
            self.task_manager.update_task(
                task_id,
                progress=13,
                message="Indexes ready"
            )

            entity_types = self._ontology_to_entity_types(ontology)
            type_names = list(entity_types.keys()) if entity_types else []
            self.task_manager.update_task(
                task_id,
                progress=14,
                message=f"Ontology loaded: {len(type_names)} entity types"
            )

            def on_split_frac(frac: float) -> None:
                self.task_manager.update_task(
                    task_id,
                    progress=round(14 + min(1.0, frac) * 6, 1),
                    message=f"Splitting document… {min(100, int(frac * 100))}%",
                )

            chunks = TextProcessor.split_text(
                text,
                chunk_size,
                chunk_overlap,
                on_progress=on_split_frac,
            )
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )

            episode_uuids = await self._add_text_batches_async(
                graphiti,
                graph_id,
                chunks,
                batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=round(20 + min(1.0, prog) * 66, 1),
                    message=msg,
                ),
                entity_types=entity_types,
            )

            self.task_manager.update_task(
                task_id,
                progress=86,
                message="Waiting for processing to complete..."
            )

            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=round(86 + min(1.0, prog) * 9, 1),
                    message=msg,
                ),
            )

            self.task_manager.update_task(
                task_id,
                progress=96,
                message="Fetching graph information..."
            )

            graph_info = await self._get_graph_info_async(graph_id)
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
        except Exception as e:
            import traceback
            self.task_manager.fail_task(task_id, f"{str(e)}\n{traceback.format_exc()}")
        finally:
            if graphiti is not None:
                await graphiti.close()

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

    def _create_graphiti(self) -> Graphiti:
        if not Config.NEO4J_URI or not Config.NEO4J_USER or not Config.NEO4J_PASSWORD:
            raise ValueError("NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD must be configured for Graphiti")
        llm_client = create_graphiti_llm_client()
        embedder = create_graphiti_embedder()
        reranker = create_graphiti_reranker(embedder)

        return Graphiti(
            uri=Config.NEO4J_URI,
            user=Config.NEO4J_USER,
            password=Config.NEO4J_PASSWORD,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker,
        )

    def create_graph(self, name: str) -> str:
        return f"mirofish_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _ontology_to_entity_types(ontology: Dict[str, Any]) -> Optional[Dict[str, Type[BaseModel]]]:
        """Convert a MiroFish ontology dict into Graphiti's entity_types format.

        Graphiti expects ``dict[str, type[BaseModel]]`` where each key is a
        PascalCase type name and the value is a Pydantic model whose docstring
        describes the type (used by the LLM to classify extracted entities).
        """
        entity_defs = ontology.get("entity_types")
        if not entity_defs:
            return None

        entity_types: Dict[str, Type[BaseModel]] = {}
        for entity_def in entity_defs:
            name = entity_def.get("name")
            if not name:
                continue
            description = entity_def.get("description", f"A {name} entity.")

            # Build optional attribute fields from the ontology
            field_definitions: Dict[str, Any] = {}
            for attr in entity_def.get("attributes", []):
                attr_name = attr.get("name")
                if attr_name:
                    field_definitions[attr_name] = (
                        Optional[str],
                        Field(default=None, description=attr.get("description", attr_name)),
                    )

            # Dynamically create a Pydantic model class with the description as docstring
            model = type(name, (BaseModel,), {"__doc__": description, "__annotations__": {
                k: v[0] for k, v in field_definitions.items()
            }, **{k: v[1] for k, v in field_definitions.items()}})

            entity_types[name] = model

        return entity_types if entity_types else None

    async def _add_text_batches_async(
        self,
        graphiti: Graphiti,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        entity_types: Optional[Dict[str, Type[BaseModel]]] = None,
    ) -> List[str]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        if not chunks:
            if progress_callback:
                progress_callback("No chunks to process", 1.0)
            return []

        episode_uuids: List[str] = []
        total_chunks = len(chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size
        emit_stride = max(1, total_chunks // 120)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1

            for offset, chunk in enumerate(batch_chunks, start=1):
                result = await graphiti.add_episode(
                    name=f"chunk_{i + offset}",
                    episode_body=chunk,
                    source_description="MiroFish document",
                    source=EpisodeType.text,
                    reference_time=datetime.utcnow(),
                    group_id=graph_id,
                    entity_types=entity_types,
                )
                if result and result.episode and result.episode.uuid:
                    episode_uuids.append(str(result.episode.uuid))

                if progress_callback:
                    done = i + offset
                    ratio = done / total_chunks
                    if (
                        done == 1
                        or done == total_chunks
                        or total_chunks <= 60
                        or done % emit_stride == 0
                    ):
                        progress_callback(
                            f"Chunk {done}/{total_chunks} (batch {batch_num}/{total_batches})",
                            ratio,
                        )

        return episode_uuids

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        phase_hook: Optional[Callable[[str], None]] = None,
    ) -> List[str]:
        async def _impl() -> List[str]:
            graphiti = self._create_graphiti()
            try:
                if phase_hook:
                    phase_hook("indices_start")
                await graphiti.build_indices_and_constraints()
                if phase_hook:
                    phase_hook("indices_end")
                return await self._add_text_batches_async(
                    graphiti,
                    graph_id,
                    chunks,
                    batch_size,
                    progress_callback,
                )
            finally:
                await graphiti.close()

        return self._run_async(_impl())

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        if progress_callback:
            progress_callback("Processing complete", 1.0)

    async def _get_graph_info_async(self, graph_id: str) -> GraphInfo:
        nodes = await fetch_all_nodes_async(graph_id)
        edges = await fetch_all_edges_async(graph_id)
        entity_types = sorted({
            label
            for node in nodes
            for label in (node.labels or [])
            if label not in _GENERIC_LABELS
        })
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=entity_types,
        )

    def _stringify(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "iso_format"):
            return value.iso_format()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = fetch_all_nodes(graph_id)
        edges = fetch_all_edges(graph_id)
        node_map = {node.uuid_: node.name or "" for node in nodes}

        nodes_data = [{
            "uuid": node.uuid_,
            "name": node.name or "",
            "labels": node.labels or [],
            "summary": node.summary or "",
            "attributes": node.attributes or {},
            "created_at": self._stringify(node.created_at),
        } for node in nodes]

        edges_data = [{
            "uuid": edge.uuid_,
            "name": edge.name or "",
            "fact": edge.fact or "",
            "fact_type": edge.name or "",
            "source_node_uuid": edge.source_node_uuid,
            "target_node_uuid": edge.target_node_uuid,
            "source_node_name": edge.source_node_name or node_map.get(edge.source_node_uuid, ""),
            "target_node_name": edge.target_node_name or node_map.get(edge.target_node_uuid, ""),
            "attributes": edge.attributes or {},
            "created_at": self._stringify(edge.created_at),
            "valid_at": self._stringify(edge.valid_at),
            "invalid_at": self._stringify(edge.invalid_at),
            "expired_at": self._stringify(edge.expired_at),
            "episodes": edge.episodes or [],
        } for edge in edges]

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        delete_graph_group(graph_id)
