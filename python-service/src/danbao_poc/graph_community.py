from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any


def detect_weighted_communities(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_iterations: int = 20,
) -> list[dict[str, Any]]:
    """Deterministic weighted label propagation without a GDS dependency."""
    node_by_key = {str(node.get("node_key")): node for node in nodes if node.get("node_key")}
    adjacency: dict[str, dict[str, float]] = {key: {} for key in node_by_key}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_by_key or target not in node_by_key or source == target:
            continue
        weight = max(0.05, float(edge.get("weight") or 0.5))
        adjacency[source][target] = adjacency[source].get(target, 0.0) + weight
        adjacency[target][source] = adjacency[target].get(source, 0.0) + weight

    labels = {key: key for key in node_by_key}
    for _ in range(max(1, min(max_iterations, 100))):
        changed = False
        for key in sorted(node_by_key):
            neighbours = adjacency.get(key) or {}
            if not neighbours:
                continue
            scores: dict[str, float] = defaultdict(float)
            for neighbour, weight in neighbours.items():
                scores[labels[neighbour]] += weight
            best_label = min(scores, key=lambda label: (-scores[label], label))
            if best_label != labels[key]:
                labels[key] = best_label
                changed = True
        if not changed:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    for key, label in labels.items():
        groups[label].append(key)
    result: list[dict[str, Any]] = []
    for members in sorted(groups.values(), key=lambda values: (-len(values), values)):
        members = sorted(members)
        member_set = set(members)
        internal_edges = [
            edge for edge in edges
            if edge.get("source") in member_set and edge.get("target") in member_set
        ]
        degree = {
            member: sum(adjacency.get(member, {}).get(other, 0.0) for other in member_set)
            for member in members
        }
        ranked_members = sorted(members, key=lambda member: (-degree[member], member))
        result.append({
            "member_keys": members,
            "ranked_member_keys": ranked_members,
            "internal_edges": internal_edges,
            "density": round((2 * len(internal_edges)) / max(1, len(members) * (len(members) - 1)), 4),
        })
    return result


def assign_stable_community_keys(
    communities: list[dict[str, Any]],
    previous_memberships: dict[str, set[str]],
    *,
    kb_id: int,
    overlap_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    unused_previous = set(previous_memberships)
    for community in communities:
        members = set(community.get("member_keys") or [])
        best_key = None
        best_score = 0.0
        for community_key in sorted(unused_previous):
            previous = previous_memberships[community_key]
            score = len(members & previous) / max(1, len(members | previous))
            if score > best_score:
                best_key = community_key
                best_score = score
        if best_key and best_score >= overlap_threshold:
            community_key = best_key
            unused_previous.remove(best_key)
        else:
            digest = hashlib.sha1("|".join(sorted(members)).encode("utf-8")).hexdigest()[:16]
            community_key = f"community:{kb_id}:{digest}"
        community["community_key"] = community_key
        community["previous_overlap"] = round(best_score, 4)
    return communities


def build_community_report(
    community: dict[str, Any],
    node_by_key: dict[str, dict[str, Any]],
    *,
    max_findings: int = 8,
) -> dict[str, Any]:
    ranked = community.get("ranked_member_keys") or community.get("member_keys") or []
    names = [str((node_by_key.get(key) or {}).get("name") or key) for key in ranked]
    title = "、".join(names[:3]) or "未命名主题"
    findings: list[str] = []
    for edge in community.get("internal_edges") or []:
        source_name = str((node_by_key.get(str(edge.get("source"))) or {}).get("name") or edge.get("source"))
        target_name = str((node_by_key.get(str(edge.get("target"))) or {}).get("name") or edge.get("target"))
        predicate = str(edge.get("predicate") or edge.get("type") or "RELATED_TO")
        finding = f"{source_name} --{predicate}--> {target_name}"
        if finding not in findings:
            findings.append(finding)
        if len(findings) >= max_findings:
            break
    summary = f"该主题聚合了 {len(ranked)} 个知识对象，核心对象包括：{'、'.join(names[:6])}。"
    if findings:
        summary += f" 主要关系：{'；'.join(findings[:4])}。"
    return {
        "title": title,
        "summary": summary,
        "findings": findings,
        "member_count": len(ranked),
        "relation_count": len(community.get("internal_edges") or []),
        "density": community.get("density") or 0.0,
    }
