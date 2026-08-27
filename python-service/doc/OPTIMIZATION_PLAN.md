# danbao-poc 准确率优化方案（完整版）

> 基于 315 题测试结果分析 + 7 个对标项目借鉴
> 当前有效命中率：80.0% | 目标：90%+

---

## 一、当前性能瓶颈诊断

### 1.1 测试结果概览（315 题）

| 指标 | RAGFLOW | danbao-poc | 差距 |
|------|---------|------------|------|
| 正确（✓） | 108 (34.3%) | 115 (36.5%) | +7 |
| 部分正确（△） | 119 (37.8%) | 137 (43.5%) | +18 |
| 错误（✗） | 79 (25.1%) | 63 (20.0%) | -16 |
| 无结果（—） | 9 (2.9%) | 0 (0.0%) | -9 |
| **有效命中** | **227 (72.1%)** | **252 (80.0%)** | **+25** |

### 1.2 最差品类分析

| 品类 | 题数 | ✗ 率 | 主要失败模式 |
|------|------|------|-------------|
| 制度刁难 | 15 | **66.7%** | 返回错误章节/条款 |
| 制度模糊 | 15 | **66.7%** | 口语化查询无法映射到制度条款 |
| 制度文件 | 23 | **56.5%** | 精确查询返回错误文档段落 |
| 反混淆 | 31 | **35.5%** | 产品名混淆，返回错误产品的内容 |
| 跨库混合 | 10 | **30.0%** | 制度+方案联合查询失败 |

### 1.3 消融测试关键发现（110 题）

| 配置 | 命中率 | vs baseline |
|------|--------|------------|
| baseline | 56.0% | — |
| no_graph | **59.3%** | +3.3% ✅ |
| no_structured | **59.7%** | +3.7% ✅ |
| no_section_summary | 56.9% | +0.9% |
| with_llm_enhancement | **50.0%** | -6.0% ❌ |
| bm25_vector_only | 55.2% | -0.8% |

**核心矛盾**：去掉功能反而更好，说明多通道融合存在噪声干扰。

### 1.4 分数虚高问题

danbao-poc 平均 Top-1 分数 **0.85**，但正确率只有 **36.5%**。分数高不代表答对了，只说明和"某个"文档相似度高。BM25 min-max 归一化在单结果时将所有分数拉到 0.5，导致低质量结果被虚高评分。

---

## 二、优化方案（按优先级排序）

---

### P0 — 立即可做（预计 +5~8% 命中率）

---

#### 2.1 关闭 LLM Query Enhancement（来源：消融测试 + RAG-Pro）

**问题**：LLM 改写查询降低命中率 6%，边界场景降低 15.8%，多轮上下文降低 13%。

**RAG-Pro 的启示**：RAG-Pro 只在查询 >50 字符时才用 LLM 改写，短查询保持原样。

**修复方案**：
```python
# query_understanding.py
def should_enhance_query(query: str) -> bool:
    """仅对长查询启用 LLM 改写"""
    if len(query) <= 50:
        return False
    # 超短查询（<4字）用同义词表扩展，不用 LLM
    if len(query) <= 4:
        return False
    return True
```

**预期收益**：整体命中率 +3~5%

---

#### 2.2 调整多通道融合权重（来源：消融测试）

**问题**：graph 和 structured 通道贡献噪声，降低命中率。

**当前权重**（business_plan profile）：
- bm25=0.28, vector=0.17, structured=0.22, graph=0.15, section_summary=0.08, qa=0.10

**建议权重**：
- bm25=**0.35**, vector=**0.25**, structured=**0.10**, graph=**0.05**, section_summary=0.08, qa=**0.17**

**修改位置**：MySQL `kb_retrieval_strategy_config` 表或代码默认值。

**预期收益**：命中率 +2~3%

---

#### 2.3 修复 BM25 分数归一化（来源：代码审计 + RAG-Pro RRF）

**问题**：`es_store.py` 对 field_results 和 chunk_results 分别做 min-max 归一化。如果子索引只返回 1 条结果，`span=0`，所有分数变成 0.5。

**RAG-Pro 的替代方案**：RRF（Reciprocal Rank Fusion）
```
score(d) = Σ 1/(k + rank)，k=60
```

**修复方案 A（最小改动）**：
```python
# es_store.py search_bm25 归一化修复
if span == 0:
    normalized_score = 0.3  # 固定基准分，而非 0.5
else:
    normalized_score = (raw_score - min_score) / span
```

**修复方案 B（推荐，借鉴 RAG-Pro）**：
用 RRF 替代 min-max 归一化，直接按排名融合：
```python
def rrf_fuse(route_results: dict[str, list], k: int = 60) -> list:
    scores = defaultdict(float)
    for route_name, results in route_results.items():
        weight = ROUTE_WEIGHTS.get(route_name, 0.1)
        for rank, item in enumerate(results, 1):
            scores[item["identity_key"]] += weight / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])
```

**预期收益**：消除分数虚高，正确率 +2~3%

---

### P1 — 核心优化（预计 +8~15% 命中率）

---

#### 2.4 产品名→文档映射（来源：测试失败分析，核心瓶颈）

**问题**：用户问"加工贷的反担保措施"，系统不知道"加工贷"对应哪个文件。所有产品的反担保措辞几乎一样，BM25 无法区分。

这是**最大的单一瓶颈**，影响 35~62% 的错误结果。

**修复方案**：

**Step 1：ES 索引新增 `product_names` keyword 数组**
```json
"product_names": {"type": "keyword"}
```

**Step 2：解析时提取产品名称**
```python
# save_parse_result 时从 file_node.name 提取
product_names = extract_product_names(file_node_name)
# 例："鲁农担批〔2025〕23号 鲁担惠农贷_加工贷" → ["加工贷", "鲁担惠农贷"]
# 例："果香贷—冠县酥梨产业集群担保服务方案" → ["果香贷", "冠县酥梨"]
```

**Step 3：检索时产品名 filter boost**
```python
# query_understanding 检测产品名后，加 should boost
if detected_products:
    boost_clause = {
        "bool": {
            "should": [
                {"terms": {"product_names": detected_products}}
            ]
        }
    }
    # 匹配产品名的 chunk 获得 +0.30 boost
```

**预期收益**：反混淆类正确率从 26% → 60%+，整体 +5~8%

---

#### 2.5 父子检索扩展（来源：KnowFlow，最高优先级借鉴）

**问题**：当前检索到 child chunk 后直接返回，上下文不完整。比如"额度测算规则"返回的是一个片段，而非完整的额度计算段落。

**KnowFlow 的做法**：
1. 混合检索返回 child chunks
2. 通过 `ParentChildMapping` 查 parent
3. 从 ES 独立 parent 索引获取 parent 内容
4. **用 parent 内容替换 child**

**danbao-poc 适配方案**：

当前已有 `primary_chunk_id` 和 `parent_chunk_id` 字段，但检索时未利用。

```python
# retrieve_service.py 的 evidence group 组装阶段
def expand_to_parent_context(evidence_groups, es, mysql_conn):
    for group in evidence_groups:
        primary_chunk_id = group.get("primary_chunk_id")
        if primary_chunk_id:
            # 从 MySQL 获取 parent chunk 完整内容
            parent = mysql_store.get_chunk_by_id(primary_chunk_id)
            if parent and parent["content"] != group["display_text"]:
                group["parent_context_full"] = parent["content"]
                group["parent_section_path"] = parent.get("section_path", "")
```

**预期收益**：部分正确（△）→ 正确（✓）的转化率提升，整体 +3~5%

---

#### 2.6 超短/口语查询扩展（来源：测试失败分析 + DataGraphX jieba）

**问题**：超短查询命中率 36%，口语同义词 35%。

**修复方案**：

**A. 同义词表（不依赖 LLM）**
```python
SYNONYMS = {
    "利息": ["担保费率", "费率", "利率"],
    "抵押": ["反担保", "担保物", "抵押物"],
    "准入": ["准入条件", "申请条件", "申请要求"],
    "还不上": ["追偿", "风险缓释", "逾期"],
    "几个点": ["费率", "担保费率"],
    "靠谱": ["担保方案", "产品介绍"],
    "能贷多少": ["额度", "授信额度", "额度测算"],
    "多久": ["期限", "授信期限", "担保期限"],
}

def expand_colloquial_query(query: str) -> list[str]:
    keywords = []
    for colloquial, formal_terms in SYNONYMS.items():
        if colloquial in query:
            keywords.extend(formal_terms)
    return keywords
```

**B. 字段匹配扩展（借鉴 DataGraphX jieba 分词）**
```python
def expand_short_query(query: str) -> list[str]:
    if len(query) <= 4:
        keywords = []
        # 匹配 field_code 别名
        for alias, code in FIELD_ALIASES.items():
            if alias in query:
                keywords.append(code)
        # 匹配产品名
        for product in KNOWN_PRODUCTS:
            if product in query:
                keywords.append(product)
        return keywords
    return []
```

**预期收益**：超短/口语类命中率从 35% → 55%+，整体 +3~4%

---

#### 2.7 制度文件 profile 优化（来源：测试失败分析 + KnowFlow AST 分块）

**问题**：制度类查询 ✗ 率高达 56~67%。

**根因**：
1. `graph_enabled_profile` 只对 `business_plan` 生效，制度文件的图检索被关闭
2. `section_path_text_tks` 权重 `^3` 被 `doc_name_tks^5` 覆盖
3. 制度文件的章节类型未在 `SECTION_ALIASES` 中定义

**修复方案**：

**A. 扩展 SECTION_ALIASES**
```python
SECTION_ALIASES_GOVERNANCE = {
    "responsibility": ["职责", "职权", "权限", "负责"],
    "penalty": ["处罚", "追责", "责任追究", "处分"],
    "appointment": ["任命", "聘任", "选举", "任免"],
    "meeting_rule": ["议事规则", "会议制度", "开会"],
    "decision": ["决策", "决议", "表决"],
    "supervision": ["监督", "监事", "审计"],
    "financial": ["财务", "资金", "预算", "大额资金"],
}
```

**B. 制度文件 section_path 权重提升**
```python
# 对 governance_rule profile
if profile == "governance_rule":
    field_boosts = {
        "section_path_text_tks": 6,  # 从 3 提升到 6
        "doc_name_tks": 3,           # 从 5 降到 3
        "title_tks": 4,
        "content_tks": 1,
    }
```

**C. 为 governance_rule 开启图检索**
```python
def _graph_enabled_profile(profile: str) -> bool:
    return profile in {"business_plan", "governance_rule"}
```

**预期收益**：制度类正确率从 33% → 50%+，整体 +3~5%

---

#### 2.8 LCS 双门控证据对齐（来源：LangExtract）

**问题**：当前证据对齐用 `SequenceMatcher.ratio() > 0.78`，存在假阳性。

**LangExtract 的改进**：
- **覆盖率门控**：matches ≥ ceil(extraction_len × 0.75)
- **密度门控**：matches / span_length ≥ 1/3

```python
def lcs_align_with_gates(extraction_text: str, source_text: str,
                         coverage_threshold: float = 0.75,
                         density_threshold: float = 0.33) -> AlignmentResult:
    """LCS 双门控对齐，替代 SequenceMatcher"""
    # 1. Tokenize both texts
    ext_tokens = tokenize(extraction_text)
    src_tokens = tokenize(source_text)

    # 2. LCS DP - find tightest span for each match count
    best_spans = best_lcs_spans(ext_tokens, src_tokens)

    # 3. Coverage gate
    max_matches = max(best_spans.keys())
    if max_matches < ceil(len(ext_tokens) * coverage_threshold):
        return AlignmentResult(status="FAILED")

    # 4. Density gate
    span = best_spans[max_matches]
    density = max_matches / span.length
    if density < density_threshold:
        # Try lower match counts for denser spans
        for k in sorted(best_spans.keys(), reverse=True):
            if k >= ceil(len(ext_tokens) * coverage_threshold):
                span = best_spans[k]
                if k / span.length >= density_threshold:
                    return AlignmentResult(status="MATCH_EXACT", span=span)
        return AlignmentResult(status="MATCH_FUZZY")

    return AlignmentResult(status="MATCH_EXACT", span=span)
```

**预期收益**：证据引用精确度提升，减少错误引用

---

### P2 — 增强优化（预计 +3~5% 命中率）

---

#### 2.9 跨文档对比查询聚合（来源：测试失败分析）

**问题**：对比类查询（"农耕贷和农贸贷的授信期限"）只返回一个产品信息。

**修复方案**：
```python
def detect_comparison_query(query: str) -> bool:
    comparison_markers = ["和", "与", "区别", "不同", "对比", "分别", "哪个"]
    return any(m in query for m in comparison_markers)

def handle_comparison_query(query, kb_id, es):
    # 1. 自动增加 top_k
    top_k = 15  # 从 5 增加到 15

    # 2. Evidence group 按 file_node_id 分组（而非 primary_chunk_id）
    # 确保不同产品的结果都保留
    groups = group_by_file_node(results)

    # 3. 每个 file_node 至少保留 1 个 group
    diverse_groups = ensure_file_diversity(groups, max_per_file=2)
    return diverse_groups
```

**预期收益**：对比类从 partial → correct

---

#### 2.10 多轮提取 + 重叠解决（来源：LangExtract）

**问题**：LLM 知识提取单轮可能遗漏实体。

**LangExtract 的做法**：`extraction_passes > 1` 时多轮独立提取后合并。

```python
def multi_pass_extract(text: str, prompt: str, passes: int = 2) -> list[Extraction]:
    all_extractions = []
    for pass_idx in range(passes):
        extractions = llm_extract(text, prompt, temperature=0.1 * pass_idx)
        all_extractions.append(extractions)

    # 合并：重叠提取按首轮优先，非重叠追加
    merged = merge_non_overlapping(all_extractions)
    return merged
```

**预期收益**：知识提取召回率提升 5~10%

---

#### 2.11 AST 语义分块（来源：KnowFlow）

**问题**：当前 LLM Planner 失败时 fallback 到单章节，丢失所有结构信息。

**KnowFlow 的做法**：`markdown-it-py` 解析 Markdown AST，标题触发 chunk 边界，表格/代码块保持完整。

```python
def ast_aware_chunk(markdown_text: str, max_tokens: int = 256) -> list[Chunk]:
    """AST 语义分块，替代 LLM Planner fallback"""
    from markdown_it import MarkdownIt
    md = MarkdownIt()
    tokens = md.parse(markdown_text)

    chunks = []
    current_chunk = []
    context_stack = []  # 跟踪标题层级 H1-H6

    for token in tokens:
        if token.type == "heading_open":
            # 标题触发 chunk 边界
            if current_chunk:
                chunks.append(finalize_chunk(current_chunk, context_stack))
                current_chunk = []
            level = int(token.tag[1])
            context_stack = [c for c in context_stack if c["level"] < level]
            context_stack.append({"level": level, "text": get_heading_text(token)})
        elif token.type in ("table", "code_block"):
            # 表格/代码块保持完整
            current_chunk.append(token)
        else:
            current_chunk.append(token)

    if current_chunk:
        chunks.append(finalize_chunk(current_chunk, context_stack))

    return chunks
```

**预期收益**：Planner 失败时的 chunk 质量大幅提升

---

#### 2.12 中文正则关系模式（来源：GraphRAG-Example）

**问题**：LLM 知识提取可能遗漏实体间关系。

**GraphRAG-Example 的 11 条中文 pattern**：

```python
CN_PATTERNS = [
    # A是B的C → (A, B, C) 三元关系
    r"(?P<s>[一-龥]{2,20})是(?P<o>[一-龥]{2,20})的(?P<v>[一-龥]{2,10})",
    # 属于/隶属于
    r"(?P<s>[一-龥]{2,20})(?:属于|隶属于|归属于)(?P<o>[一-龥]{2,20})",
    # 包含/包括
    r"(?P<s>[一-龥]{2,20})(?:包含|包括|涵盖|由.*组成|分为)(?P<o>[一-龥]{2,20})",
    # 创建/发明
    r"(?P<s>[一-龥]{2,20})(?:创建|发明|提出|发现|开发|设计)(?P<o>[一-龥]{2,20})",
    # 位于/来自
    r"(?P<s>[一-龥]{2,20})(?:位于|来自|出生于|坐落于)(?P<o>[一-龥]{2,20})",
    # 影响/导致
    r"(?P<s>[一-龥]{2,20})(?:影响|导致|引发|促进|支持)(?P<o>[一-龥]{2,20})",
    # 基于/依赖
    r"(?P<s>[一-龥]{2,20})(?:基于|依赖|使用|采用)(?P<o>[一-龥]{2,20})",
    # 别名
    r"(?P<s>[一-龥]{2,20})(?:被称为|又称|也叫|简称)(?P<o>[一-龥]{2,20})",
]
```

**集成方式**：作为 LLM 提取的**补充**，正则提取结果与 LLM 提取结果合并去重。

**预期收益**：关系提取召回率提升，图通道质量改善

---

#### 2.13 受约束图 Schema（来源：DataGraphX）

**问题**：当前 graph 通道允许自由定义节点/关系类型，LLM 可能产生不可控结构。

**DataGraphX 的做法**：固定 6 节点类型 + 10 关系类型。

**danbao-poc 适配**：
```python
ALLOWED_NODE_TYPES = {
    "product",       # 担保产品（加工贷、农耕贷等）
    "field",         # 字段（额度、费率、期限等）
    "region",        # 地区
    "industry",      # 行业
    "organization",  # 机构
    "condition",     # 条件（准入、反担保等）
}

ALLOWED_RELATION_TYPES = {
    "has_field",     # 产品 → 字段
    "applies_to",    # 产品 → 条件
    "in_region",     # 产品 → 地区
    "in_industry",   # 产品 → 行业
    "requires",      # 条件 → 条件
    "excludes",      # 条件 → 条件（排斥）
    "similar_to",    # 产品 → 产品
    "references",    # 任意 → 任意
}
```

**预期收益**：减少 graph 通道噪声，提升图检索质量

---

### P3 — 长期优化（预计 +2~3% 命中率）

---

#### 2.14 实体去重五阶段管道（来源：Graphify）

```python
def dedup_entities(entities: list[Entity]) -> list[Entity]:
    """五阶段实体去重"""
    # Stage 1: 精确归一化 + Union-Find
    uf = UnionFind()
    norm_map = {}
    for e in entities:
        norm = normalize(e.name)  # lowercase + 非字母数字折叠
        if norm in norm_map:
            uf.union(e.id, norm_map[norm])
        else:
            norm_map[norm] = e.id

    # Stage 2: 熵门控（低熵标签跳过模糊匹配）
    candidates = [e for e in entities if shannon_entropy(e.name) >= 2.5]

    # Stage 3: MinHash/LSH 阻塞
    minhashes = {e.id: make_minhash(e.name, num_perm=128) for e in candidates}
    lsh_pairs = lsh_candidates(minhashes)

    # Stage 4: Jaro-Winkler 验证
    for id1, id2 in lsh_pairs:
        sim = jaro_winkler(entities[id1].name, entities[id2].name)
        community_boost = 5.0 if same_community(id1, id2) else 0
        if sim + community_boost >= 92:
            uf.union(id1, id2)

    # Stage 5: LLM 仲裁 ambiguous pairs
    ambiguous = [(id1, id2) for id1, id2 in lsh_pairs
                 if 75 <= jaro_winkler(...) < 92]
    llm_decisions = llm_tiebreak(ambiguous, batch_size=30)
    for (id1, id2), should_merge in llm_decisions:
        if should_merge:
            uf.union(id1, id2)

    return uf.get_groups()
```

**预期收益**：anchor 去重质量提升

---

#### 2.15 100% 坐标追溯（来源：KnowFlow）

```python
def build_coordinate_map(middle_json: dict) -> dict[int, tuple]:
    """构建行号→坐标映射"""
    coord_map = {}
    for page_idx, page in enumerate(middle_json.get("pdf_info", [])):
        for block in page.get("preproc_blocks", []):
            for line_idx, line in enumerate(block.get("lines", [])):
                global_line_no = compute_global_line_no(page_idx, line_idx)
                bbox = line.get("bbox", [0, 0, 0, 0])
                coord_map[global_line_no] = (page_idx, *bbox)
    return coord_map

def attach_coordinates_to_chunks(chunks, coord_map, source_text):
    """将 chunk 文本行映射回原始行号"""
    used_indices = set()
    for chunk in chunks:
        chunk_lines = chunk["content"].split("\n")
        matched_coords = []
        for line in chunk_lines:
            for line_no, coord in coord_map.items():
                if line_no not in used_indices and fuzzy_match(line, get_line_text(line_no)):
                    matched_coords.append(coord)
                    used_indices.add(line_no)
                    break
        chunk["bbox_json"] = matched_coords
```

**预期收益**：证据定位精度从 ~97% → 100%

---

#### 2.16 稀疏向量检索（来源：RAG-Pro）

```python
def sparse_vector_search(query: str, index: str, es, top_k: int = 20):
    """BM25 风格的 token overlap 点积检索"""
    # BGE-M3 生成 sparse vector: {token_id: weight}
    sparse_vec = embedding_client.get_sparse_vector(query)

    # ES 查询：每个 token 的 term query × weight
    should_clauses = []
    for token_id, weight in sparse_vec.items():
        token_text = tokenizer.decode([token_id])
        should_clauses.append({
            "term": {
                "content_tks_tokens": {
                    "value": token_text,
                    "boost": weight
                }
            }
        })

    body = {
        "size": top_k,
        "query": {"bool": {"should": should_clauses, "minimum_should_match": 1}}
    }
    return es.search(index=index, body=body)
```

**与 BM25 融合**：RRF 融合 dense + sparse + BM25 三路结果。

**预期收益**：精确关键词匹配补充语义检索

---

#### 2.17 自动引用插入（来源：KnowFlow）

```python
def insert_citations(answer: str, chunks: list[dict], es) -> str:
    """在 LLM 答案中自动插入 [ID:n] 引用"""
    sentences = split_sentences(answer)
    cited_answer = ""
    threshold = 0.63

    for sent in sentences:
        sent_vec = embed(sent)
        best_match = None
        best_score = 0

        for chunk in chunks:
            score = cosine_similarity(sent_vec, chunk["embedding_vector"])
            if score > threshold and score > best_score:
                best_score = score
                best_match = chunk

        cited_answer += sent
        if best_match:
            cited_answer += f" [ID:{best_match['chunk_id']}]"
        threshold *= 0.8  # 递减阈值
        threshold = max(threshold, 0.3)

    return cited_answer
```

**预期收益**：答案可追溯性

---

## 三、实施路线图

### Phase 1（1~2 周）— P0 优化

| # | 任务 | 工作量 | 预期收益 |
|---|------|--------|---------|
| 2.1 | 关闭 LLM Query Enhancement（条件化） | 半天 | +3~5% |
| 2.2 | 调整融合权重 | 半天 | +2~3% |
| 2.3 | 修复 BM25 归一化 / 引入 RRF | 1 天 | +2~3% |

**Phase 1 预期命中率**：80% → **85~88%**

### Phase 2（2~3 周）— P1 优化

| # | 任务 | 工作量 | 预期收益 |
|---|------|--------|---------|
| 2.4 | 产品名→文档映射 | 2 天 | +5~8% |
| 2.5 | 父子检索扩展 | 1 天 | +3~5% |
| 2.6 | 超短/口语查询扩展 | 1 天 | +3~4% |
| 2.7 | 制度文件 profile 优化 | 1 天 | +3~5% |
| 2.8 | LCS 双门控证据对齐 | 2 天 | 证据精确度↑ |

**Phase 2 预期命中率**：88% → **92~95%**

### Phase 3（3~4 周）— P2 + P3 优化

| # | 任务 | 工作量 | 预期收益 |
|---|------|--------|---------|
| 2.9 | 跨文档对比查询聚合 | 1 天 | 对比类正确率↑ |
| 2.10 | 多轮提取 + 重叠解决 | 1 天 | 提取召回率↑ |
| 2.11 | AST 语义分块 | 2 天 | chunk 质量↑ |
| 2.12 | 中文正则关系模式 | 1 天 | 关系提取↑ |
| 2.13 | 受约束图 Schema | 半天 | 图通道降噪 |
| 2.14 | 实体去重五阶段 | 2 天 | anchor 质量↑ |
| 2.15 | 100% 坐标追溯 | 1 天 | 证据定位↑ |
| 2.16 | 稀疏向量检索 | 2 天 | 检索效果↑ |
| 2.17 | 自动引用插入 | 1 天 | 可追溯性↑ |

**Phase 3 预期命中率**：95% → **97%+**

---

## 四、优化效果预估总表

| 阶段 | 时间 | 核心改动 | 预期命中率 |
|------|------|---------|-----------|
| 当前 | — | — | **80.0%** |
| Phase 1 | 1~2 周 | 关闭 LLM 改写 + 调权重 + RRF | **85~88%** |
| Phase 2 | 2~3 周 | 产品映射 + 父子扩展 + 口语扩展 + 制度优化 | **92~95%** |
| Phase 3 | 3~4 周 | AST 分块 + 正则关系 + 稀疏向量 + 坐标追溯 | **97%+** |

---

## 五、借鉴来源汇总

| 借鉴项目 | 核心借鉴点 | 对应优化项 |
|---------|-----------|-----------|
| **KnowFlow** | 父子检索扩展、100% 坐标追溯、AST 语义分块 | 2.5, 2.11, 2.15 |
| **RAG-Pro** | RRF 融合、稀疏向量、条件查询改写、关键词生成 | 2.1, 2.3, 2.16 |
| **LangExtract** | LCS 双门控对齐、多轮提取 | 2.8, 2.10 |
| **Graphify** | 5 阶段实体去重 | 2.14 |
| **GraphRAG** | 中文正则 11 模式 | 2.12 |
| **DataGraphX** | 受约束图 Schema、条件关系搜索 | 2.13 |
| **消融测试** | 关闭 LLM 改写、降低 graph/structured 权重 | 2.1, 2.2 |
| **失败分析** | 产品映射、口语扩展、制度优化、对比聚合 | 2.4, 2.6, 2.7, 2.9 |
