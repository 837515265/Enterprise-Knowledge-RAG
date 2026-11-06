# Algorithm map — Enterprise Knowledge RAG

[Home](../README.md) · [简体中文](../README.zh-CN.md) · [Reproducibility](REPRODUCIBILITY.md)

This is a **code-reading guide**, not a claim of academic novelty or measured performance. It links the implemented approaches to their source and identifies how to evaluate them. Several components are inspired by established techniques; the value of the system lies in their integration, domain adaptation, and evidence governance.

## 1. Structured document chunking

**Source:** [ast_chunker.py](../python-service/src/danbao_poc/ast_chunker.py), [catalog_chunker.py](../python-service/src/danbao_poc/catalog_chunker.py), [chunker.py](../python-service/src/danbao_poc/chunker.py)

- The AST-oriented chunker recognizes headings, numbered clauses, fenced code, and Markdown tables.
- Code/table regions are marked as protected units so a generic text splitter need not fragment them arbitrarily.
- Catalog and container-oriented strategies provide alternative chunk boundaries for domain documents.

**Why it matters:** A clause, table row, or API example can lose meaning if retrieval cuts across its structural boundary.

**How to test:** Compare fixed-size, AST, and catalog strategies on the same labeled question set. Report retrieval Recall@5/10, answer correctness, and percentage of tables/clauses split across chunks.

## 2. Entity/anchor deduplication

**Source:** [anchor_deduper.py](../python-service/src/danbao_poc/anchor_deduper.py)

The implementation uses Chinese-aware normalization, an entropy check, character shingles, a deterministic MinHash signature, LSH candidate buckets, and fuzzy comparison. Candidate pairs can be merged while retaining aliases and source metadata.

**Why it matters:** Duplicate names increase graph noise, but aggressive merging can incorrectly combine distinct products or policy entities.

**How to test:** Publish labeled positive and hard-negative pairs. Report candidate recall, merge precision/recall/F1, runtime, and false merges by entity type.

## 3. Graph communities and stable identity

**Source:** [graph_community.py](../python-service/src/danbao_poc/graph_community.py), [graph_builder.py](../python-service/src/danbao_poc/graph_builder.py)

- Deterministic weighted label propagation identifies communities without requiring the Neo4j GDS plugin.
- Membership overlap with previous snapshots can preserve community keys; otherwise keys derive from a stable digest of members.
- Reports summarize prominent nodes and internal relations.

**Why it matters:** Topic-level graph navigation is more useful when groups are stable enough to audit and compare after re-indexing.

**How to test:** Measure community stability after document updates, relation precision, size distribution, and the effect on multi-hop question retrieval.

## 4. Query-aware, multi-channel retrieval

**Source:** [retrieval_plan.py](../python-service/src/danbao_poc/retrieval_plan.py), [query.py](../python-service/src/danbao_poc/query.py), [es_store.py](../python-service/src/danbao_poc/es_store.py)

The retrieval plan includes six possible channels: QA, structured fields, section summaries, graph, BM25, and dense vectors. A plan can depend on the document profile and query features. The query module defines rank-fusion parameters, channel weights, and reranking logic.

**Important distinction:** A configured channel or profile does not by itself prove that every combination is integrated and tested end to end.

**How to test:** Compare (a) BM25 only, (b) vector only, (c) BM25+vector, (d) all enabled channels, (e) routing on/off, and (f) reranking on/off. Use a fixed corpus, identical query set, and consistent indexing state. Report Recall@k, MRR/nDCG, p50/p95 retrieval latency, and token/model cost.

## 5. Evidence-span alignment

**Source:** [evidence_aligner.py](../python-service/src/danbao_poc/evidence_aligner.py), [citation_formatter.py](../python-service/src/danbao_poc/citation_formatter.py)

Alignment tries an exact substring match, a whitespace-normalized match, and a longest-common-subsequence fallback. Coverage and density thresholds help reject suspicious dispersed matches; character offsets can connect a quote to the source.

**Why it matters:** An answer with a citation is only trustworthy when the cited passage really supports the statement.

**How to test:** Label answer claims with supporting passages and page/character spans. Report exact-span match rate, citation precision, unsupported-claim rate, and false-positive alignments. Test OCR noise, duplicate passages, and cross-page citations.

## 6. What would establish a credible technical claim?

A public benchmark should include:

1. **Dataset:** licensed/sample documents, query categories, reference answers, and gold evidence locations.
2. **Configuration:** model names and versions, embedding dimensions, ES mappings, chunk lengths, retrieval weights, prompts, and hardware.
3. **Baselines:** simple vector-only RAG and BM25+vector RAG.
4. **Ablations:** one algorithm turned off at a time.
5. **Results:** per-category metrics, latency, cost, failures, and repeated-run variation.
6. **Reproduction:** commands, sanitized configs, and deterministic evaluation scripts.

A good claim is *“On the published N-question test set, strategy A scored X vs baseline Y under config Z.”* Without these artifacts, describe capabilities as implementations, not proven accuracy gains.

## Engineering constraints to disclose

- Python service documentation currently describes an integration path focused on the \`guarantee_plan\` workflow.
- Some Java parent/dependency artifacts and the file center are external to this repository.
- There is currently no verified independent end-to-end demo or published benchmark in this source snapshot.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the exact missing pieces.
