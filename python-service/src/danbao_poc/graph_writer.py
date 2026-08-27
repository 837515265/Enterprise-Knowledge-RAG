from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any

from danbao_poc.graph_schema import RELATION_WEIGHT_BY_TYPE

EDGE_TYPE_WEIGHTS = RELATION_WEIGHT_BY_TYPE


def _edge_key(edge_type: str, from_node_key: str, to_node_key: str) -> str:
    raw = f"{edge_type}|{from_node_key}|{to_node_key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def edge_weight(edge_type: str | None, confidence: Any = None) -> float:
    base = EDGE_TYPE_WEIGHTS.get(str(edge_type or ""), 0.60)
    try:
        if confidence is not None:
            base = max(base, min(1.0, float(confidence)))
    except Exception:
        pass
    return round(max(0.05, min(1.0, base)), 4)


def driver(uri: str, user: str, password: str):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(uri, auth=(user, password))


def apply_constraints(uri: str, user: str, password: str, cypher_text: str) -> None:
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            for statement in [item.strip() for item in cypher_text.split(";") if item.strip()]:
                session.run(statement)
    finally:
        drv.close()


def delete_file_graph(uri: str, user: str, password: str, kb_id: int, file_node_id: int) -> None:
    """Delete file-private subgraph without touching shared dimension nodes.

    Shared dimension nodes (Region/Industry/Organization) are keyed without
    file_node_id, so matching file_node_id deletes only the document-local graph
    and detaches any old relationships left by previous importer versions.
    """
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            # Relationships are owned by the file that produced their evidence.
            # Delete them explicitly so shared↔shared facts cannot survive a
            # document deletion or reparse.
            session.run(
                """
                MATCH ()-[r]->()
                WHERE r.kb_id = $kb_id AND r.file_node_id = $file_node_id
                DELETE r
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
            )
            session.run(
                """
                MATCH (n {kb_id: $kb_id, file_node_id: $file_node_id})
                DETACH DELETE n
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
            )
            session.run(
                """
                MATCH (shared {kb_id: $kb_id})
                WHERE shared.file_node_id IS NULL
                  AND NOT shared:File
                  AND NOT (shared)--()
                DELETE shared
                """,
                kb_id=kb_id,
            )
    finally:
        drv.close()


def sync_file_graph_delta(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    file_node_id: int,
    file_name: str,
    parse_generation: str,
    index_generation: str,
    graph_nodes: list[dict[str, Any]],
    graph_edges: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Prune stale file-owned graph items, then MERGE the current snapshot."""
    private_node_keys = [
        str(node.get("node_key"))
        for node in graph_nodes
        if node.get("node_key")
        and node.get("node_type") not in _SHARED_NODE_TYPES
        and node.get("node_type") not in {"File", "Chunk"}
    ]
    chunk_ids = [int(row["id"]) for row in chunk_rows if row.get("id") is not None]
    chunk_key_to_id = {
        str(row.get("chunk_key") or row.get("id")): row.get("id")
        for row in chunk_rows
        if row.get("id") is not None
    }
    edge_keys: list[str] = []
    for edge in graph_edges:
        edge_type = str(edge.get("edge_type") or "RELATED_TO")
        target_key = str(edge.get("to_node_key") or "")
        if edge_type == "EVIDENCED_BY":
            chunk_id = chunk_key_to_id.get(str(edge.get("source_chunk_key") or ""))
            if chunk_id is not None:
                target_key = f"chunk:{chunk_id}"
        edge_keys.append(_edge_key(edge_type, str(edge.get("from_node_key") or ""), target_key))
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            stale_relationships = int(session.run(
                """
                MATCH ()-[rel]->()
                WHERE rel.kb_id = $kb_id AND rel.file_node_id = $file_node_id
                  AND (rel.edge_key IS NULL OR NOT rel.edge_key IN $edge_keys)
                WITH collect(rel) AS stale
                FOREACH (rel IN stale | DELETE rel)
                RETURN size(stale) AS deleted
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                edge_keys=edge_keys,
            ).single()["deleted"])
            stale_nodes = int(session.run(
                """
                MATCH (node {kb_id: $kb_id, file_node_id: $file_node_id})
                WHERE NOT node:File AND NOT node:Chunk
                  AND (node.node_key IS NULL OR NOT node.node_key IN $node_keys)
                WITH collect(node) AS stale
                FOREACH (node IN stale | DETACH DELETE node)
                RETURN size(stale) AS deleted
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                node_keys=private_node_keys,
            ).single()["deleted"])
            stale_chunks = int(session.run(
                """
                MATCH (chunk:Chunk {kb_id: $kb_id, file_node_id: $file_node_id})
                WHERE NOT chunk.chunk_id IN $chunk_ids
                WITH collect(chunk) AS stale
                FOREACH (chunk IN stale | DETACH DELETE chunk)
                RETURN size(stale) AS deleted
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                chunk_ids=chunk_ids,
            ).single()["deleted"])
    finally:
        drv.close()
    import_knowledge_graph(
        uri,
        user,
        password,
        kb_id,
        file_node_id,
        file_name,
        parse_generation,
        index_generation,
        graph_nodes,
        graph_edges,
        chunk_rows,
    )
    return {
        "staleRelationshipsDeleted": stale_relationships,
        "staleNodesDeleted": stale_nodes,
        "staleChunksDeleted": stale_chunks,
    }


def load_file_graph(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    file_node_id: int,
    *,
    include_chunks: bool = False,
    limit: int = 160,
) -> dict[str, Any]:
    """Load a bounded, read-only document subgraph for the knowledge workbench."""
    node_limit = max(1, min(int(limit), 300))
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            node_rows = list(
                session.run(
                    """
                    MATCH (n {kb_id: $kb_id, file_node_id: $file_node_id})
                    WHERE $include_chunks OR NOT n:Chunk
                    WITH n ORDER BY CASE WHEN n:File THEN 0 WHEN n:Document THEN 1 ELSE 2 END, coalesce(n.name_cn, n.title_cn, n.node_key, '')
                    LIMIT $limit
                    OPTIONAL MATCH (n)-[]-(shared {kb_id: $kb_id})
                    WHERE shared.file_node_id IS NULL AND ($include_chunks OR NOT shared:Chunk)
                    WITH collect(DISTINCT n) + collect(DISTINCT shared) AS candidates
                    UNWIND candidates AS candidate
                    WITH DISTINCT candidate WHERE candidate IS NOT NULL
                    RETURN elementId(candidate) AS id, labels(candidate) AS labels, properties(candidate) AS properties
                    LIMIT $limit
                    """,
                    kb_id=kb_id,
                    file_node_id=file_node_id,
                    include_chunks=include_chunks,
                    limit=node_limit,
                )
            )
            nodes: list[dict[str, Any]] = []
            node_ids: list[str] = []
            for row in node_rows:
                props = dict(row["properties"] or {})
                labels = list(row["labels"] or [])
                node_id = str(row["id"])
                node_ids.append(node_id)
                nodes.append(
                    {
                        "id": node_id,
                        "type": labels[0] if labels else "Entity",
                        "labels": labels,
                        "name": props.get("name_cn") or props.get("title_cn") or props.get("node_key") or props.get("content_preview") or "未命名实体",
                        "description": props.get("summary_cn") or props.get("value_text") or props.get("content_preview") or props.get("description") or "",
                        "pageStart": props.get("page_start"),
                        "pageEnd": props.get("page_end"),
                        "chunkId": props.get("chunk_id"),
                        "properties": {key: _graph_json_value(value) for key, value in props.items()},
                    }
                )

            edges: list[dict[str, Any]] = []
            if node_ids:
                edge_rows = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE elementId(a) IN $node_ids AND elementId(b) IN $node_ids
                    RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target,
                           type(r) AS type, properties(r) AS properties
                    LIMIT 600
                    """,
                    node_ids=node_ids,
                )
                for row in edge_rows:
                    edges.append(
                        {
                            "id": str(row["id"]),
                            "source": str(row["source"]),
                            "target": str(row["target"]),
                            "type": str(row["type"]),
                            "properties": {
                                key: _graph_json_value(value) for key, value in dict(row["properties"] or {}).items()
                            },
                        }
                    )

            return {
                "kbId": str(kb_id),
                "fileNodeId": str(file_node_id),
                "includeChunks": include_chunks,
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "nodeCount": len(nodes),
                    "relationCount": len(edges),
                    "nodeTypes": dict(Counter(node["type"] for node in nodes)),
                    "relationTypes": dict(Counter(edge["type"] for edge in edges)),
                },
            }
    finally:
        drv.close()


def load_kb_graph(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    *,
    include_chunks: bool = False,
    limit: int = 120,
) -> dict[str, Any]:
    """Load a bounded knowledge-base subgraph for the KB overview workspace.

    File and document roots are ordered first so the returned graph keeps its
    document context even when a knowledge base contains many business nodes.
    Chunk nodes stay opt-in because they can otherwise dominate the overview.
    """
    node_limit = max(1, min(int(limit), 400))
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            node_rows = list(
                session.run(
                    """
                    MATCH (n {kb_id: $kb_id})
                    WHERE $include_chunks OR NOT n:Chunk
                    WITH n
                    ORDER BY CASE
                               WHEN n:File THEN 0
                               WHEN n:Document THEN 1
                               WHEN n.file_node_id IS NULL THEN 2
                               ELSE 3
                             END,
                             coalesce(n.name_cn, n.title_cn, n.node_key, '')
                    LIMIT $limit
                    RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties
                    """,
                    kb_id=kb_id,
                    include_chunks=include_chunks,
                    limit=node_limit,
                )
            )
            nodes: list[dict[str, Any]] = []
            node_ids: list[str] = []
            file_node_ids: set[str] = set()
            for row in node_rows:
                props = dict(row["properties"] or {})
                labels = list(row["labels"] or [])
                node_id = str(row["id"])
                node_ids.append(node_id)
                if props.get("file_node_id") is not None:
                    file_node_ids.add(str(props["file_node_id"]))
                nodes.append(
                    {
                        "id": node_id,
                        "type": labels[0] if labels else "Entity",
                        "labels": labels,
                        "name": props.get("name_cn") or props.get("title_cn") or props.get("node_key") or props.get("content_preview") or "未命名实体",
                        "description": props.get("summary_cn") or props.get("value_text") or props.get("content_preview") or props.get("description") or "",
                        "pageStart": props.get("page_start"),
                        "pageEnd": props.get("page_end"),
                        "chunkId": props.get("chunk_id"),
                        "fileNodeId": props.get("file_node_id"),
                        "properties": {key: _graph_json_value(value) for key, value in props.items()},
                    }
                )

            edges: list[dict[str, Any]] = []
            if node_ids:
                edge_rows = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE elementId(a) IN $node_ids AND elementId(b) IN $node_ids
                    RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target,
                           type(r) AS type, properties(r) AS properties
                    LIMIT 1000
                    """,
                    node_ids=node_ids,
                )
                for row in edge_rows:
                    edges.append(
                        {
                            "id": str(row["id"]),
                            "source": str(row["source"]),
                            "target": str(row["target"]),
                            "type": str(row["type"]),
                            "properties": {
                                key: _graph_json_value(value) for key, value in dict(row["properties"] or {}).items()
                            },
                        }
                    )

            return {
                "kbId": str(kb_id),
                "includeChunks": include_chunks,
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "nodeCount": len(nodes),
                    "relationCount": len(edges),
                    "fileCount": len(file_node_ids),
                    "nodeTypes": dict(Counter(node["type"] for node in nodes)),
                    "relationTypes": dict(Counter(edge["type"] for edge in edges)),
                },
            }
    finally:
        drv.close()


def audit_kb_graph(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    *,
    hub_degree: int = 20,
    limit: int = 100,
) -> dict[str, Any]:
    """Return a read-only graph quality report for one knowledge base.

    The surprise score follows graphify's governance idea: ambiguous facts,
    cross-document facts, cross-community links and peripheral-to-hub links are
    surfaced for review. File/Chunk/Community infrastructure nodes are excluded
    from hub and isolate diagnostics.
    """
    hub_degree = max(3, min(int(hub_degree), 500))
    row_limit = max(1, min(int(limit), 500))
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            node_count = int(session.run(
                "MATCH (n {kb_id: $kb_id}) RETURN count(n) AS total",
                kb_id=kb_id,
            ).single()["total"])
            edge_count = int(session.run(
                "MATCH ()-[r]->() WHERE r.kb_id = $kb_id RETURN count(r) AS total",
                kb_id=kb_id,
            ).single()["total"])
            hubs = [
                {
                    "nodeKey": row["node_key"],
                    "name": row["name"],
                    "labels": list(row["labels"] or []),
                    "degree": int(row["degree"] or 0),
                }
                for row in session.run(
                    """
                    MATCH (n {kb_id: $kb_id})-[r]-()
                    WHERE NOT n:File AND NOT n:Chunk AND NOT n:GraphCommunity
                    WITH n, count(r) AS degree
                    WHERE degree >= $hub_degree
                    RETURN n.node_key AS node_key,
                           coalesce(n.name_cn, n.title_cn, n.node_key) AS name,
                           labels(n) AS labels,
                           degree
                    ORDER BY degree DESC
                    LIMIT $limit
                    """,
                    kb_id=kb_id,
                    hub_degree=hub_degree,
                    limit=row_limit,
                )
            ]
            isolates = [
                {
                    "nodeKey": row["node_key"],
                    "name": row["name"],
                    "labels": list(row["labels"] or []),
                }
                for row in session.run(
                    """
                    MATCH (n {kb_id: $kb_id})
                    WHERE NOT n:File AND NOT n:Chunk AND NOT n:GraphCommunity
                      AND NOT (n)--()
                    RETURN n.node_key AS node_key,
                           coalesce(n.name_cn, n.title_cn, n.node_key) AS name,
                           labels(n) AS labels
                    ORDER BY name
                    LIMIT $limit
                    """,
                    kb_id=kb_id,
                    limit=row_limit,
                )
            ]
            assertion_rows = session.run(
                """
                MATCH (assertion:Assertion {kb_id: $kb_id})
                OPTIONAL MATCH (subject)-[:ASSERTS]->(assertion)
                OPTIONAL MATCH (assertion)-[semantic]->(object)
                WHERE type(semantic) <> 'EVIDENCED_BY'
                  AND type(semantic) <> 'MEMBER_OF_COMMUNITY'
                WITH assertion, subject, object, semantic,
                     size([(subject)--() | 1]) AS subject_degree,
                     size([(object)--() | 1]) AS object_degree,
                     [(assertion)-[:EVIDENCED_BY]->(c:Chunk) | c.file_node_id]
                       + [(subject)-[:EVIDENCED_BY]->(sc:Chunk) | sc.file_node_id]
                       + [(object)-[:EVIDENCED_BY]->(oc:Chunk) | oc.file_node_id] AS evidence_files,
                     [(subject)-[:MEMBER_OF_COMMUNITY]->(scom:GraphCommunity) | scom.community_key] AS subject_communities,
                     [(object)-[:MEMBER_OF_COMMUNITY]->(ocom:GraphCommunity) | ocom.community_key] AS object_communities
                RETURN assertion.node_key AS assertion_key,
                       assertion.relation_id AS relation_id,
                       assertion.confidence_label AS confidence_label,
                       assertion.confidence AS confidence,
                       assertion.file_node_id AS file_node_id,
                       coalesce(subject.name_cn, assertion.subject_name, subject.node_key) AS subject_name,
                       coalesce(object.name_cn, assertion.object_name, object.node_key) AS object_name,
                       coalesce(assertion.predicate, type(semantic), 'RELATED_TO') AS predicate,
                       subject_degree, object_degree, evidence_files,
                       subject_communities, object_communities,
                       coalesce(assertion.evidence_quote, assertion.value_text, '') AS evidence_quote,
                       subject IS NULL AS missing_subject,
                       object IS NULL AS missing_object,
                       NOT (assertion)-[:EVIDENCED_BY]->(:Chunk) AS missing_evidence
                LIMIT $limit
                """,
                kb_id=kb_id,
                limit=max(row_limit * 10, 1000),
            )
            surprises: list[dict[str, Any]] = []
            orphan_assertions: list[dict[str, Any]] = []
            confidence_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0, "UNKNOWN": 0}
            for row in assertion_rows:
                confidence_label = str(row["confidence_label"] or "UNKNOWN").upper()
                if confidence_label not in confidence_counts:
                    confidence_label = "UNKNOWN"
                confidence_counts[confidence_label] += 1
                missing = bool(row["missing_subject"] or row["missing_object"] or row["missing_evidence"])
                item = {
                    "assertionKey": row["assertion_key"],
                    "relationId": row["relation_id"],
                    "subject": row["subject_name"],
                    "predicate": row["predicate"],
                    "object": row["object_name"],
                    "confidenceLabel": confidence_label,
                    "confidence": float(row["confidence"] or 0.0),
                    "fileNodeId": row["file_node_id"],
                    "evidenceQuote": row["evidence_quote"] or "",
                }
                if missing:
                    orphan_assertions.append({
                        **item,
                        "missingSubject": bool(row["missing_subject"]),
                        "missingObject": bool(row["missing_object"]),
                        "missingEvidence": bool(row["missing_evidence"]),
                    })
                score = 0
                reasons: list[str] = []
                if confidence_label == "AMBIGUOUS":
                    score += 3
                    reasons.append("ambiguous_relation")
                evidence_files = {value for value in (row["evidence_files"] or []) if value is not None}
                if len(evidence_files) > 1:
                    score += 2
                    reasons.append("cross_document_evidence")
                subject_communities = set(row["subject_communities"] or [])
                object_communities = set(row["object_communities"] or [])
                if subject_communities and object_communities and subject_communities.isdisjoint(object_communities):
                    score += 1
                    reasons.append("cross_community")
                subject_degree = int(row["subject_degree"] or 0)
                object_degree = int(row["object_degree"] or 0)
                if min(subject_degree, object_degree) <= 2 and max(subject_degree, object_degree) >= hub_degree:
                    score += 1
                    reasons.append("peripheral_to_hub")
                if str(row["predicate"] or "") == "RELATED_TO":
                    score += 1
                    reasons.append("generic_relation")
                if score:
                    surprises.append({**item, "surpriseScore": score, "reasons": reasons})
            surprises.sort(key=lambda item: (-int(item["surpriseScore"]), float(item["confidence"])))
            return {
                "kbId": str(kb_id),
                "status": "healthy" if not orphan_assertions and not surprises else "needs_attention",
                "stats": {
                    "nodeCount": node_count,
                    "relationCount": edge_count,
                    "assertionCount": sum(confidence_counts.values()),
                    "hubCount": len(hubs),
                    "isolateCount": len(isolates),
                    "orphanAssertionCount": len(orphan_assertions),
                    "surpriseCount": len(surprises),
                    "confidenceLabels": confidence_counts,
                },
                "hubs": hubs,
                "isolates": isolates,
                "orphanAssertions": orphan_assertions[:row_limit],
                "surprises": surprises[:row_limit],
                "thresholds": {"hubDegree": hub_degree, "limit": row_limit},
            }
    finally:
        drv.close()


def rebuild_kb_communities(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    *,
    min_size: int = 2,
) -> dict[str, Any]:
    """Rebuild KB communities while reusing IDs by membership overlap."""
    from danbao_poc.graph_community import (
        assign_stable_community_keys,
        build_community_report,
        detect_weighted_communities,
    )

    min_size = max(1, min(int(min_size), 20))
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            previous: dict[str, set[str]] = {}
            for row in session.run(
                """
                MATCH (n {kb_id: $kb_id})-[:MEMBER_OF_COMMUNITY]->(community:GraphCommunity {kb_id: $kb_id})
                RETURN community.community_key AS community_key, collect(DISTINCT n.node_key) AS member_keys
                """,
                kb_id=kb_id,
            ):
                previous[str(row["community_key"])] = {str(key) for key in (row["member_keys"] or []) if key}

            node_rows = list(session.run(
                """
                MATCH (n {kb_id: $kb_id})
                WHERE n.node_key IS NOT NULL
                  AND NOT n:File AND NOT n:Chunk AND NOT n:Assertion AND NOT n:GraphCommunity
                RETURN n.node_key AS node_key,
                       coalesce(n.name_cn, n.title_cn, n.value_text, n.node_key) AS name,
                       labels(n) AS labels,
                       n.file_node_id AS file_node_id
                """,
                kb_id=kb_id,
            ))
            nodes = [dict(row) for row in node_rows]
            node_by_key = {str(node["node_key"]): node for node in nodes}
            edges: list[dict[str, Any]] = []
            for row in session.run(
                """
                MATCH (source {kb_id: $kb_id})-[rel]->(target {kb_id: $kb_id})
                WHERE source.node_key IS NOT NULL AND target.node_key IS NOT NULL
                  AND NOT source:Assertion AND NOT target:Assertion
                  AND NOT source:File AND NOT target:File
                  AND NOT source:Chunk AND NOT target:Chunk
                  AND type(rel) NOT IN ['EVIDENCED_BY', 'PARSED_INTO', 'MENTIONS', 'ASSERTS', 'MEMBER_OF_COMMUNITY']
                RETURN source.node_key AS source, target.node_key AS target,
                       type(rel) AS type, coalesce(rel.weight, rel.confidence, 0.5) AS weight
                """,
                kb_id=kb_id,
            ):
                edges.append(dict(row))
            for row in session.run(
                """
                MATCH (source {kb_id: $kb_id})-[:ASSERTS]->(assertion:Assertion {kb_id: $kb_id})-[rel]->(target {kb_id: $kb_id})
                WHERE type(rel) NOT IN ['EVIDENCED_BY', 'MEMBER_OF_COMMUNITY']
                  AND source.node_key IS NOT NULL AND target.node_key IS NOT NULL
                RETURN source.node_key AS source, target.node_key AS target,
                       type(rel) AS type,
                       coalesce(assertion.predicate, type(rel)) AS predicate,
                       coalesce(rel.weight, assertion.confidence, 0.5) AS weight,
                       assertion.relation_id AS relation_id
                """,
                kb_id=kb_id,
            ):
                edges.append(dict(row))

            communities = [
                community for community in detect_weighted_communities(nodes, edges)
                if len(community.get("member_keys") or []) >= min_size
            ]
            assign_stable_community_keys(communities, previous, kb_id=kb_id)

            session.run(
                "MATCH ()-[rel:MEMBER_OF_COMMUNITY]->(community:GraphCommunity {kb_id: $kb_id}) DELETE rel",
                kb_id=kb_id,
            )
            session.run(
                "MATCH (community:GraphCommunity {kb_id: $kb_id}) DETACH DELETE community",
                kb_id=kb_id,
            )
            member_count = 0
            for community in communities:
                report = build_community_report(community, node_by_key)
                community_key = str(community["community_key"])
                session.run(
                    """
                    MERGE (community:GraphCommunity {kb_id: $kb_id, community_key: $community_key})
                    SET community.title_cn = $title,
                        community.summary_cn = $summary,
                        community.findings = $findings,
                        community.member_count = $member_count,
                        community.relation_count = $relation_count,
                        community.density = $density,
                        community.previous_overlap = $previous_overlap,
                        community.report_version = 'community_report_v1',
                        community.updated_at = datetime()
                    """,
                    kb_id=kb_id,
                    community_key=community_key,
                    title=report["title"],
                    summary=report["summary"],
                    findings=report["findings"],
                    member_count=report["member_count"],
                    relation_count=report["relation_count"],
                    density=report["density"],
                    previous_overlap=community.get("previous_overlap") or 0.0,
                )
                for node_key in community.get("member_keys") or []:
                    session.run(
                        """
                        MATCH (node {kb_id: $kb_id, node_key: $node_key})
                        MATCH (community:GraphCommunity {kb_id: $kb_id, community_key: $community_key})
                        MERGE (node)-[rel:MEMBER_OF_COMMUNITY]->(community)
                        SET rel.kb_id = $kb_id, rel.updated_at = datetime()
                        """,
                        kb_id=kb_id,
                        node_key=node_key,
                        community_key=community_key,
                    )
                    member_count += 1
            return {
                "kbId": str(kb_id),
                "communityCount": len(communities),
                "memberCount": member_count,
                "previousCommunityCount": len(previous),
                "algorithm": "deterministic_weighted_label_propagation",
                "reportVersion": "community_report_v1",
            }
    finally:
        drv.close()


def search_community_reports(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Retrieve precomputed community reports for opt-in global graph search."""
    from danbao_poc.tokenizer import tokenize_text

    top_k = max(1, min(int(top_k), 30))
    query_terms = {term.lower() for term in tokenize_text(str(query or "")).split() if len(term) >= 2}
    global_intent_terms = {"整体", "全局", "概述", "总结", "主题", "知识库", "哪些", "主要", "所有"}
    substantive_terms = query_terms - global_intent_terms
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            records = session.run(
                """
                MATCH (community:GraphCommunity {kb_id: $kb_id})
                OPTIONAL MATCH (member)-[:MEMBER_OF_COMMUNITY]->(community)
                OPTIONAL MATCH (member)-[:EVIDENCED_BY]->(chunk:Chunk)
                WITH community, collect(DISTINCT chunk)[0] AS evidence_chunk
                RETURN community.community_key AS community_key,
                       community.title_cn AS title,
                       community.summary_cn AS summary,
                       community.findings AS findings,
                       community.member_count AS member_count,
                       community.relation_count AS relation_count,
                       community.density AS density,
                       evidence_chunk.chunk_id AS chunk_id,
                       evidence_chunk.file_node_id AS file_node_id,
                       evidence_chunk.page_start AS page_no
                ORDER BY community.member_count DESC, community.density DESC
                LIMIT 100
                """,
                kb_id=kb_id,
            )
            rows: list[dict[str, Any]] = []
            for record in records:
                row = dict(record)
                findings = [str(item) for item in (row.get("findings") or []) if item]
                content = "\n".join([str(row.get("summary") or ""), *[f"- {item}" for item in findings]]).strip()
                searchable = f"{row.get('title') or ''} {content}".lower()
                matched = sum(1 for term in query_terms if term in searchable)
                lexical = matched / max(1, len(query_terms)) if query_terms else 0.0
                structural = min(1.0, float(row.get("member_count") or 0) / 20.0)
                substantive_match = any(term in searchable for term in substantive_terms)
                score = 0.0 if substantive_terms and not substantive_match else min(0.99, 0.50 + lexical * 0.35 + structural * 0.10)
                rows.append({
                    "kb_id": kb_id,
                    "chunk_id": row.get("chunk_id"),
                    "file_node_id": row.get("file_node_id"),
                    "page_no": row.get("page_no"),
                    "title": row.get("title") or "知识库全局主题",
                    "content": content,
                    "snippet": content,
                    "score": score,
                    "route": "graph_global",
                    "type": "community_report",
                    "hit_type": "community_report",
                    "match_type": "community_report",
                    "community_key": row.get("community_key"),
                    "community_report": {
                        "communityKey": row.get("community_key"),
                        "title": row.get("title"),
                        "summary": row.get("summary"),
                        "findings": findings,
                        "memberCount": row.get("member_count"),
                        "relationCount": row.get("relation_count"),
                        "density": row.get("density"),
                    },
                })
            rows = [row for row in rows if float(row.get("score") or 0.0) > 0.0]
            rows.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
            return rows[:top_k]
    finally:
        drv.close()


def _graph_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_graph_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _graph_json_value(item) for key, item in value.items()}
    return str(value)


def import_business_graph(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    file_node_id: int,
    file_name: str,
    parse_generation: str,
    index_generation: str,
    graph_nodes: list[dict[str, Any]],
    graph_edges: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
    field_rows: list[dict[str, Any]],
    mention_rows: list[dict[str, Any]],
) -> None:
    drv = driver(uri, user, password)
    field_map = {row["id"]: row for row in field_rows}
    mention_map = {row["field_id"]: row for row in mention_rows}
    chunk_map = {row["id"]: row for row in chunk_rows}
    node_type_map = {row["node_key"]: row["node_type"] for row in graph_nodes}
    try:
        with drv.session() as session:
            session.run(
                """
                MERGE (f:File {kb_id: $kb_id, file_node_id: $file_node_id})
                SET f.name_cn = $file_name, f.parse_generation = $parse_generation, f.index_generation = $index_generation, f.updated_at = datetime()
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                file_name=file_name,
                parse_generation=parse_generation,
                index_generation=index_generation,
            )
            for node in graph_nodes:
                labels = node["node_type"]
                if labels == "BusinessPlan":
                    session.run(
                        """
                        MERGE (n:BusinessPlan {kb_id: $kb_id, file_node_id: $file_node_id, node_key: $node_key})
                        SET n.name_cn = $name_cn, n.value_text = $value_text, n.parse_generation = $parse_generation, n.index_generation = $index_generation
                        WITH n
                        MATCH (f:File {kb_id: $kb_id, file_node_id: $file_node_id})
                        MERGE (f)-[r:PARSED_AS]->(n)
                        SET r.parse_generation = $parse_generation, r.index_generation = $index_generation, r.weight = $weight
                        """,
                        kb_id=kb_id,
                        file_node_id=file_node_id,
                        node_key=node["node_key"],
                        name_cn=node.get("name_cn"),
                        value_text=node.get("value_text"),
                        parse_generation=parse_generation,
                        index_generation=index_generation,
                        weight=edge_weight("PARSED_AS"),
                    )
                elif labels == "BusinessField":
                    source_field_id = node.get("source_field_id")
                    field_row = field_map.get(source_field_id)
                    mention = mention_map.get(source_field_id, {})
                    session.run(
                        """
                        MERGE (n:BusinessField {kb_id: $kb_id, file_node_id: $file_node_id, node_key: $node_key})
                        SET n.name_cn = $name_cn,
                            n.value_text = $value_text,
                            n.field_code = $field_code,
                            n.parse_generation = $parse_generation,
                            n.index_generation = $index_generation
                        """,
                        kb_id=kb_id,
                        file_node_id=file_node_id,
                        node_key=node["node_key"],
                        name_cn=node.get("name_cn"),
                        value_text=node.get("value_text"),
                        field_code=(field_row or {}).get("field_code"),
                        parse_generation=parse_generation,
                        index_generation=index_generation,
                    )
                    chunk_row = chunk_map.get((field_row or {}).get("source_chunk_id"))
                    if chunk_row:
                        session.run(
                            """
                            MERGE (c:Chunk {kb_id: $kb_id, file_node_id: $file_node_id, chunk_id: $chunk_id})
                            SET c.section_type = $section_type,
                                c.title_cn = $title,
                                c.content_preview = $preview,
                                c.page_start = $page_start,
                                c.page_end = $page_end,
                                c.parse_generation = $parse_generation,
                                c.index_generation = $index_generation
                            WITH c
                            MATCH (n:BusinessField {kb_id: $kb_id, file_node_id: $file_node_id, node_key: $node_key})
                            MERGE (n)-[r:EVIDENCED_BY {page_no: $page_no, evidence_text: $evidence_text}]->(c)
                            SET r.parse_generation = $parse_generation, r.index_generation = $index_generation, r.weight = $weight
                            """,
                            kb_id=kb_id,
                            file_node_id=file_node_id,
                            chunk_id=chunk_row["id"],
                            section_type=chunk_row.get("section_type"),
                            title=chunk_row.get("title"),
                            preview=(chunk_row.get("content") or "")[:500],
                            page_start=chunk_row.get("page_start"),
                            page_end=chunk_row.get("page_end"),
                            parse_generation=parse_generation,
                            index_generation=index_generation,
                            node_key=node["node_key"],
                            page_no=mention.get("page_no"),
                            evidence_text=(mention.get("evidence_text") or "")[:500],
                            weight=edge_weight("EVIDENCED_BY", (field_row or {}).get("confidence")),
                        )
                else:
                    # Shared dimension nodes (Region/Industry/Organization):
                    # MERGE on (kb_id, node_key) only — no file_node_id — so
                    # they can be shared across documents within the same KB.
                    session.run(
                        f"""
                        MERGE (n:{labels} {{kb_id: $kb_id, node_key: $node_key}})
                        SET n.name_cn = $name_cn, n.value_text = $value_text, n.parse_generation = $parse_generation, n.index_generation = $index_generation
                        """,
                        kb_id=kb_id,
                        node_key=node["node_key"],
                        name_cn=node.get("name_cn"),
                        value_text=node.get("value_text"),
                        parse_generation=parse_generation,
                        index_generation=index_generation,
                    )

            for edge in graph_edges:
                from_type = node_type_map.get(edge["from_node_key"])
                to_type = node_type_map.get(edge["to_node_key"])
                from_shared = from_type in {"Region", "Industry", "Organization"}
                to_shared = to_type in {"Region", "Industry", "Organization"}
                from_match = "{kb_id: $kb_id, node_key: $from_node_key}" if from_shared else "{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $from_node_key}"
                to_match = "{kb_id: $kb_id, node_key: $to_node_key}" if to_shared else "{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $to_node_key}"
                session.run(
                    f"""
                    MATCH (a {from_match})
                    MATCH (b {to_match})
                    MERGE (a)-[r:{edge["edge_type"]}]->(b)
                    SET r.parse_generation = $parse_generation,
                        r.index_generation = $index_generation,
                        r.weight = $weight
                    """,
                    kb_id=kb_id,
                    file_node_id=file_node_id,
                    from_node_key=edge["from_node_key"],
                    to_node_key=edge["to_node_key"],
                    parse_generation=parse_generation,
                    index_generation=index_generation,
                    weight=edge_weight(edge.get("edge_type"), (edge.get("properties") or {}).get("confidence")),
                )
    finally:
        drv.close()


def update_business_field(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    file_node_id: int,
    field_code: str,
    field_name_cn: str,
    value_text: str,
    chunk_row: dict[str, Any] | None,
    mention_row: dict[str, Any] | None,
    index_generation: str | None = None,
) -> None:
    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            session.run(
                """
                MATCH (n:BusinessField {kb_id: $kb_id, file_node_id: $file_node_id, field_code: $field_code})
                SET n.name_cn = $field_name_cn,
                    n.value_text = $value_text,
                    n.index_generation = COALESCE($index_generation, n.index_generation),
                    n.updated_at = datetime()
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                field_code=field_code,
                field_name_cn=field_name_cn,
                value_text=value_text,
                index_generation=index_generation,
            )
            if chunk_row:
                session.run(
                    """
                    MERGE (c:Chunk {kb_id: $kb_id, file_node_id: $file_node_id, chunk_id: $chunk_id})
                    SET c.section_type = $section_type,
                        c.title_cn = $title,
                        c.content_preview = $preview,
                        c.page_start = $page_start,
                        c.page_end = $page_end,
                        c.index_generation = COALESCE($index_generation, c.index_generation)
                    WITH c
                    MATCH (n:BusinessField {kb_id: $kb_id, file_node_id: $file_node_id, field_code: $field_code})
                    OPTIONAL MATCH (n)-[old:EVIDENCED_BY]->(:Chunk)
                    DELETE old
                    MERGE (n)-[r:EVIDENCED_BY {page_no: $page_no, evidence_text: $evidence_text}]->(c)
                    SET r.index_generation = COALESCE($index_generation, r.index_generation),
                        r.weight = $weight
                    """,
                    kb_id=kb_id,
                    file_node_id=file_node_id,
                    chunk_id=chunk_row["id"],
                    section_type=chunk_row.get("section_type"),
                    title=chunk_row.get("title"),
                    preview=(chunk_row.get("content") or "")[:500],
                    page_start=chunk_row.get("page_start"),
                    page_end=chunk_row.get("page_end"),
                    field_code=field_code,
                    page_no=(mention_row or {}).get("page_no"),
                    evidence_text=((mention_row or {}).get("evidence_text") or "")[:500],
                    index_generation=index_generation,
                    weight=edge_weight("EVIDENCED_BY", (mention_row or {}).get("confidence")),
                )
    finally:
        drv.close()


# ──────────────────────────────────────────────────────────────
# 通用知识图写入 (替代 import_business_graph)
# ──────────────────────────────────────────────────────────────

# KB 级稳定对象不绑定 file_node_id；同名规范化 Anchor 因而可连接
# 多份文档中的条件、职责和流程事实。Requirement/ProcessStep 等事实节点
# 仍保持文件私有，避免把相似段落误合并。
_SHARED_NODE_TYPES = {"Location", "Industry", "Organization", "Entity", "Concept", "Document"}


def import_knowledge_graph(
    uri: str,
    user: str,
    password: str,
    kb_id: int,
    file_node_id: int,
    file_name: str,
    parse_generation: str,
    index_generation: str,
    graph_nodes: list[dict[str, Any]],
    graph_edges: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
) -> None:
    """将通用知识图写入 Neo4j。

    与 import_business_graph() 的区别:
    1. 节点类型从 node_type 字段动态决定，不再硬编码
    2. MERGE + ON CREATE SET / ON MATCH SET 确保 weight 正确更新
    3. 所有关系都写入 weight 属性
    4. EVIDENCED_BY 使用 evidence_quote 而非 chunk preview
    """
    chunk_map = {str(c.get("chunk_key") or c.get("id")): c for c in chunk_rows}
    node_type_map = {n["node_key"]: n.get("node_type", "Entity") for n in graph_nodes}

    drv = driver(uri, user, password)
    try:
        with drv.session() as session:
            # ── File 节点 ────────────────────────────────────
            session.run(
                """
                MERGE (f:File {kb_id: $kb_id, file_node_id: $file_node_id})
                SET f.name_cn = $file_name,
                    f.parse_generation = $parse_generation,
                    f.index_generation = $index_generation,
                    f.updated_at = datetime()
                """,
                kb_id=kb_id,
                file_node_id=file_node_id,
                file_name=file_name,
                parse_generation=parse_generation,
                index_generation=index_generation,
            )

            # ── 业务节点 ────────────────────────────────────
            for node in graph_nodes:
                node_type = node.get("node_type", "Entity")
                if node_type == "File":
                    continue  # File 已单独处理

                is_shared = node_type in _SHARED_NODE_TYPES
                node_key = node["node_key"]
                extra_properties = _neo4j_properties(node.get("properties"))

                if node_type == "Chunk":
                    # Chunk 节点: 用 chunk_id 做唯一键
                    chunk_data = chunk_map.get(node.get("source_chunk_key") or "")
                    if chunk_data:
                        session.run(
                            """
                            MERGE (c:Chunk {kb_id: $kb_id, file_node_id: $file_node_id, chunk_id: $chunk_id})
                            SET c.section_type = $section_type,
                                c.title_cn = $title,
                                c.content_preview = $preview,
                                c.page_start = $page_start,
                                c.page_end = $page_end,
                                c.parse_generation = $parse_generation,
                                c.index_generation = $index_generation
                            """,
                            kb_id=kb_id,
                            file_node_id=file_node_id,
                            chunk_id=chunk_data["id"],
                            section_type=chunk_data.get("section_type"),
                            title=chunk_data.get("title"),
                            preview=(chunk_data.get("content") or "")[:500],
                            page_start=chunk_data.get("page_start"),
                            page_end=chunk_data.get("page_end"),
                            parse_generation=parse_generation,
                            index_generation=index_generation,
                        )
                    continue

                # 通用业务节点
                labels = node_type  # 如 Entity, Condition, Requirement, etc.
                if is_shared:
                    # 共享节点: MERGE on (kb_id, node_key)，无 file_node_id
                    session.run(
                        f"""
                        MERGE (n:{labels} {{kb_id: $kb_id, node_key: $node_key}})
                        ON CREATE SET
                            n.name_cn = $name_cn,
                            n.value_text = $value_text,
                            n.domain_type = $domain_type,
                            n.profile = $profile,
                            n.confidence = $confidence,
                            n.parse_generation = $parse_generation,
                            n.index_generation = $index_generation,
                            n.created_at = datetime()
                        ON MATCH SET
                            n.name_cn = $name_cn,
                            n.value_text = COALESCE($value_text, n.value_text),
                            n.confidence = CASE
                                WHEN $confidence > coalesce(n.confidence, 0) THEN $confidence
                                ELSE n.confidence
                            END,
                            n.updated_at = datetime()
                        SET n += $extra_properties
                        """,
                        kb_id=kb_id,
                        node_key=node_key,
                        name_cn=node.get("name_cn"),
                        value_text=node.get("value_text"),
                        domain_type=node.get("domain_type", ""),
                        profile=node.get("profile", ""),
                        confidence=_safe_float(node.get("confidence"), 0.5),
                        parse_generation=parse_generation,
                        index_generation=index_generation,
                        extra_properties=extra_properties,
                    )
                else:
                    # 文件私有节点: MERGE on (kb_id, file_node_id, node_key)
                    session.run(
                        f"""
                        MERGE (n:{labels} {{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $node_key}})
                        ON CREATE SET
                            n.name_cn = $name_cn,
                            n.value_text = $value_text,
                            n.domain_type = $domain_type,
                            n.profile = $profile,
                            n.confidence = $confidence,
                            n.parse_generation = $parse_generation,
                            n.index_generation = $index_generation,
                            n.created_at = datetime()
                        ON MATCH SET
                            n.name_cn = $name_cn,
                            n.value_text = COALESCE($value_text, n.value_text),
                            n.confidence = CASE
                                WHEN $confidence > coalesce(n.confidence, 0) THEN $confidence
                                ELSE n.confidence
                            END,
                            n.updated_at = datetime()
                        SET n += $extra_properties
                        """,
                        kb_id=kb_id,
                        file_node_id=file_node_id,
                        node_key=node_key,
                        name_cn=node.get("name_cn"),
                        value_text=node.get("value_text"),
                        domain_type=node.get("domain_type", ""),
                        profile=node.get("profile", ""),
                        confidence=_safe_float(node.get("confidence"), 0.5),
                        parse_generation=parse_generation,
                        index_generation=index_generation,
                        extra_properties=extra_properties,
                    )

            # ── 关系边 ──────────────────────────────────────
            for edge in graph_edges:
                edge_type = edge.get("edge_type", "RELATED_TO")
                from_key = edge.get("from_node_key", "")
                to_key = edge.get("to_node_key", "")

                from_type = node_type_map.get(from_key, "Entity")
                to_type = node_type_map.get(to_key, "Entity")

                # Chunk 边由 EVIDENCED_BY 特殊处理
                if to_type == "Chunk" and edge_type == "EVIDENCED_BY":
                    _merge_evidenced_by_edge(
                        session, kb_id, file_node_id,
                        from_key, from_type,
                        edge, chunk_map,
                        parse_generation, index_generation,
                    )
                    continue

                from_shared = from_type in _SHARED_NODE_TYPES
                to_shared = to_type in _SHARED_NODE_TYPES

                from_match = "{kb_id: $kb_id, node_key: $from_node_key}" if from_shared else "{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $from_node_key}"
                to_match = "{kb_id: $kb_id, node_key: $to_node_key}" if to_shared else "{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $to_node_key}"

                conf = _safe_float(edge.get("confidence"), 0.5)
                weight = edge_weight(edge_type, conf)
                edge_key = _edge_key(edge_type, from_key, to_key)
                extra_properties = _neo4j_properties(edge.get("properties"))

                session.run(
                    f"""
                    MATCH (a {from_match})
                    MATCH (b {to_match})
                    MERGE (a)-[r:{edge_type}]->(b)
                    ON CREATE SET
                        r.kb_id = $kb_id,
                        r.file_node_id = $file_node_id,
                        r.edge_key = $edge_key,
                        r.weight = $weight,
                        r.confidence = $confidence,
                        r.evidence_count = 1,
                        r.evidence_quote = $evidence_quote,
                        r.source_chunk_key = $source_chunk_key,
                        r.parse_generation = $parse_generation,
                        r.index_generation = $index_generation,
                        r.created_at = datetime()
                    ON MATCH SET
                        r.kb_id = $kb_id,
                        r.file_node_id = $file_node_id,
                        r.edge_key = $edge_key,
                        r.weight = CASE WHEN $weight > coalesce(r.weight, 0) THEN $weight ELSE r.weight END,
                        r.confidence = CASE WHEN $confidence > coalesce(r.confidence, 0) THEN $confidence ELSE r.confidence END,
                        r.evidence_count = 1,
                        r.evidence_quote = $evidence_quote,
                        r.source_chunk_key = $source_chunk_key,
                        r.parse_generation = $parse_generation,
                        r.index_generation = $index_generation,
                        r.updated_at = datetime()
                    SET r += $extra_properties
                    """,
                    kb_id=kb_id,
                    file_node_id=file_node_id,
                    from_node_key=from_key,
                    to_node_key=to_key,
                    edge_key=edge_key,
                    weight=weight,
                    confidence=conf,
                    evidence_quote=(edge.get("evidence_quote") or "")[:500],
                    source_chunk_key=str(edge.get("source_chunk_key") or ""),
                    parse_generation=parse_generation,
                    index_generation=index_generation,
                    extra_properties=extra_properties,
                )
    finally:
        drv.close()


def _merge_evidenced_by_edge(
    session: Any,
    kb_id: int,
    file_node_id: int,
    from_node_key: str,
    from_node_type: str,
    edge: dict[str, Any],
    chunk_map: dict[str, Any],
    parse_generation: str,
    index_generation: str,
) -> None:
    """写入 EVIDENCED_BY 边: 从实体节点到 Chunk。"""
    chunk_key = edge.get("source_chunk_key") or ""
    chunk_data = chunk_map.get(str(chunk_key))
    if not chunk_data:
        return

    from_shared = from_node_type in _SHARED_NODE_TYPES
    from_match = "{kb_id: $kb_id, node_key: $from_node_key}" if from_shared else "{kb_id: $kb_id, file_node_id: $file_node_id, node_key: $from_node_key}"

    conf = _safe_float(edge.get("confidence"), 0.5)
    weight = edge_weight("EVIDENCED_BY", conf)
    edge_key = _edge_key("EVIDENCED_BY", from_node_key, f"chunk:{chunk_data['id']}")
    extra_properties = _neo4j_properties(edge.get("properties"))

    session.run(
        f"""
        MATCH (a {from_match})
        MATCH (c:Chunk {{kb_id: $kb_id, file_node_id: $file_node_id, chunk_id: $chunk_id}})
        MERGE (a)-[r:EVIDENCED_BY]->(c)
        ON CREATE SET
            r.kb_id = $kb_id,
            r.file_node_id = $file_node_id,
            r.edge_key = $edge_key,
            r.weight = $weight,
            r.confidence = $confidence,
            r.evidence_quote = $evidence_quote,
            r.source_chunk_key = $source_chunk_key,
            r.parse_generation = $parse_generation,
            r.index_generation = $index_generation,
            r.created_at = datetime()
        ON MATCH SET
            r.kb_id = $kb_id,
            r.file_node_id = $file_node_id,
            r.edge_key = $edge_key,
            r.weight = CASE WHEN $weight > coalesce(r.weight, 0) THEN $weight ELSE r.weight END,
            r.confidence = CASE WHEN $confidence > coalesce(r.confidence, 0) THEN $confidence ELSE r.confidence END,
            r.evidence_quote = $evidence_quote,
            r.source_chunk_key = $source_chunk_key,
            r.parse_generation = $parse_generation,
            r.index_generation = $index_generation,
            r.updated_at = datetime()
        SET r += $extra_properties
        """,
        kb_id=kb_id,
        file_node_id=file_node_id,
        from_node_key=from_node_key,
        chunk_id=chunk_data["id"],
        weight=weight,
        confidence=conf,
        evidence_quote=(edge.get("evidence_quote") or "")[:500],
        source_chunk_key=str(edge.get("source_chunk_key") or ""),
        edge_key=edge_key,
        parse_generation=parse_generation,
        index_generation=index_generation,
        extra_properties=extra_properties,
    )


def _neo4j_properties(value: Any) -> dict[str, Any]:
    """Convert extraction metadata to Neo4j-safe scalar/list properties."""
    if not isinstance(value, dict):
        return {}
    protected = {
        "kb_id", "file_node_id", "node_key", "chunk_id",
        "parse_generation", "index_generation", "edge_key",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        key = str(key)
        if not key or key in protected or item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            result[key] = item
        elif isinstance(item, list) and all(isinstance(v, (str, int, float, bool)) for v in item):
            result[key] = item
        else:
            result[key] = json.dumps(item, ensure_ascii=False, default=str)
    return result


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default
