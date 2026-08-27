from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def prepare_graphrag_input(chunks: list[dict[str, Any]], output_dir: str | Path) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "external_chunks.csv"
    for chunk in chunks:
        chunk.setdefault("chunk_id", "chunk")
    fieldnames = [
        "id",
        "text",
        "document_id",
        "chunk_id",
        "profile",
        "section_type",
        "title_path",
        "page_start",
        "page_end",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or "chunk"
            writer.writerow(
                {
                    "id": chunk_id,
                    "text": chunk.get("content_for_embedding") or chunk.get("content") or "",
                    "document_id": chunk.get("document_id") or "",
                    "chunk_id": chunk_id,
                    "profile": chunk.get("profile") or "",
                    "section_type": chunk.get("section_type") or "",
                    "title_path": " > ".join(chunk.get("title_path") or []),
                    "page_start": chunk.get("page_start") or "",
                    "page_end": chunk.get("page_end") or "",
                }
            )
    return [str(csv_path)]


def import_graphrag_parquet_to_neo4j(
    workspace_output: str | Path,
    uri: str,
    user: str,
    password: str,
    knowledge_base_id: str,
) -> None:
    try:
        import pandas as pd
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError("Install dependencies first: uv sync --python 3.10") from exc

    workspace_output = Path(workspace_output)
    entities_path = find_existing(workspace_output, ["entities.parquet", "create_final_entities.parquet"])
    relationships_path = find_existing(workspace_output, ["relationships.parquet", "create_final_relationships.parquet"])
    reports_path = find_existing(workspace_output, ["community_reports.parquet", "create_final_community_reports.parquet"])

    drv = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with drv.session() as session:
            if entities_path:
                df = pd.read_parquet(entities_path)
                for _, row in df.iterrows():
                    title = row_value(row, "title") or row_value(row, "name")
                    if not title:
                        continue
                    entity_key = f"gr_{knowledge_base_id}_{title}"
                    session.run(
                        """
                        MERGE (e:GraphEntity {knowledge_base_id: $kb_id, entity_key: $entity_key})
                        SET e.name_cn = $name_cn,
                            e.entity_type = $entity_type,
                            e.description_cn = $description,
                            e.updated_at = datetime()
                        """,
                        entity_key=entity_key,
                        kb_id=knowledge_base_id,
                        name_cn=str(title),
                        entity_type=row_value(row, "type"),
                        description=row_value(row, "description"),
                    )

            if relationships_path:
                df = pd.read_parquet(relationships_path)
                for _, row in df.iterrows():
                    source = row_value(row, "source")
                    target = row_value(row, "target")
                    if not source or not target:
                        continue
                    session.run(
                        """
                        MERGE (s:GraphEntity {knowledge_base_id: $kb_id, entity_key: $source_key})
                        SET s.name_cn = $source
                        MERGE (t:GraphEntity {knowledge_base_id: $kb_id, entity_key: $target_key})
                        SET t.name_cn = $target
                        MERGE (s)-[r:GRAPH_RELATED_TO {knowledge_base_id: $kb_id, source: $source, target: $target}]->(t)
                        SET r.description_cn = $description,
                            r.weight = $weight,
                            r.updated_at = datetime()
                        """,
                        kb_id=knowledge_base_id,
                        source=str(source),
                        target=str(target),
                        source_key=f"gr_{knowledge_base_id}_{source}",
                        target_key=f"gr_{knowledge_base_id}_{target}",
                        description=row_value(row, "description"),
                        weight=float(row_value(row, "weight") or 0),
                    )

            if reports_path:
                df = pd.read_parquet(reports_path)
                for _, row in df.iterrows():
                    community = str(row_value(row, "community") or row_value(row, "id") or "")
                    title = row_value(row, "title") or community
                    summary = row_value(row, "summary") or row_value(row, "full_content")
                    session.run(
                        """
                        MERGE (c:GraphCommunity {knowledge_base_id: $kb_id, community_key: $community_key})
                        SET c.title_cn = $title,
                            c.summary_cn = $summary,
                            c.updated_at = datetime()
                        """,
                        community_key=f"gc_{knowledge_base_id}_{community}",
                        kb_id=knowledge_base_id,
                        title=str(title),
                        summary=str(summary or ""),
                    )
    finally:
        drv.close()


def find_existing(root: Path, names: list[str]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists():
            return path
    for path in root.rglob("*.parquet"):
        if path.name in names:
            return path
    return None


def row_value(row: Any, key: str) -> Any:
    if key not in row:
        return None
    value = row[key]
    try:
        if value != value:
            return None
    except Exception:
        pass
    return value
