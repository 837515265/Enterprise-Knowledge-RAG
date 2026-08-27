# 解析阶段问题分析报告

> 基于 `business_plan` profile 的完整 parse pipeline 审计  
> 日期：2026-06-22  
> 范围：文件解析 → 目录分块 → 多粒度 chunk → 章节构建 → 摘要 → 字段提取 → 知识抽取 → 入库

---

## 一、Pipeline 架构总览

```
文件上传
  → parse_document (文档解析 → middle_document)
  → build_catalog_driven_chunks (LLM 目录识别 + 分块)
    → build_multigranularity_chunks (small_chunk / section_chunk / parent_chunk)
  → build_sections_from_mapped_sections (章节树)
  → build_section_summaries (章节摘要)
  → extractor (字段提取)
  → extract_knowledge_structure (知识图谱锚点/单元/关系)
  → prebuild_answers (预生成 QA)
  → save_parse_result (MySQL 入库)
```

其中 **profile chunker（`chunk_guarantee_plan`）被注册但从未调用**，pipeline 无条件走 `build_catalog_driven_chunks`。

---

## 二、问题清单

### 🔴 严重问题

#### #1 section_chunk / parent_chunk 生成条件过严，父子层级断裂

**位置**：`chunk_generation.py:350, 394`

**现象**：

```python
# section_chunk 跳过条件
if len(children) <= 1:
    continue   # 只生成 small_chunk，不生成 section 层

# parent_chunk 跳过条件
if not parent_section_id or len({child.get("section_id") for child in children}) <= 1:
    continue   # 子 section 数 ≤1，不生成 parent 层
```

业务方案文档每个 section 通常只产出 1 个 small_chunk，导致：
- `section_chunk` 数量为 **0**
- `parent_chunk` 虽然生成了 43 个，但无法通过 section 层链接到 small_chunk

**影响**：

```
期望的链路：small_chunk → section_chunk → parent_chunk
实际的链路：small_chunk ↛ NULL ↛ parent_chunk (断裂)
```

- `parent_chunk_id` 全为 NULL
- `section_context` / `parent_context` 关系不生成
- 检索时 `_choose_context` 找不到父级上下文，降级为 `adjacent_next`（仅取相邻 chunk）
- 给 LLM 的 `answer_context` 缺少更大范围的完整信息

**建议处理**：

方案 A（推荐）：当 `section_chunk` 不存在时，让 `parent_chunk` 直接关联 `small_chunk`：

```python
# mysql_store.py:1158 — 已修复 ✅
if chunk.get("chunk_type") not in {"section_chunk", "parent_chunk"}:
    continue
```

方案 B：放宽 section_chunk 生成条件，允许单 child 也生成：

```python
# chunk_generation.py:350
if len(children) < 1:   # 原来是 <= 1
    continue
```

**建议同时做 A+B**，既保证新数据有完整层级，也兼容历史数据。

---

#### #2 目录识别失败时整篇文档坍塌为 1 个 chunk

**位置**：`catalog_chunker.py:964, 1178-1228`

**现象**：

```python
# 当 anchor_locate_rate < 0.55 或 coverage < 0.35 时触发 fallback
# split_fallback=False 时，整个文档成为一个 chunk
chunks = [{
    "chunk_key": "raw_001",
    "chunk_type": "original",
    "section_type": "raw_text",
    "content": merged_text,  # 整篇文档
    "summary": merged_text[:180],  # 仅文档标题
}]
```

**影响**：

- 20 页业务方案变成一个 chunk，所有结构化信息丢失
- 字段提取阶段只能看到全局文本，精度严重下降
- 检索时命中这个 chunk 返回整篇文档内容，毫无定位能力
- summary 仅 180 字符（文档标题），章节摘要阶段基本无效

**建议处理**：

1. 提高 fallback 健壮性：`split_fallback` 默认 `true`，按页或按标题切分
2. 降低 fallback 触发阈值（`locate_rate < 0.4`、`coverage < 0.2`）或增加重试机制
3. fallback 摘要改为段落级而非全文 180 字符

---

#### #3 `_is_generic_anchor` 误杀业务核心锚点

**位置**：`knowledge_extractor.py:154`

**现象**：

```python
GENERIC_ANCHOR_TEXTS = {"额度", "期限", "流程", "条件", "范围", "对象", "主体", ...}

def _is_generic_anchor(name: str) -> bool:
    return name in GENERIC_ANCHOR_TEXTS or _CLAUSE_NUMBER_RE.match(name)
```

在 `normalize_knowledge_payload` 中，命中此函数的 anchor 被**静默丢弃**：

```python
if _is_generic_anchor(anchor_name):
    continue  # 丢弃！
```

**影响**：

| 被丢弃的词 | 在业务方案中的实际含义 |
|-----------|-------------------|
| 额度 | 授信额度、贷款额度上限 |
| 期限 | 担保期限、贷款期限 |
| 流程 | 申请流程、审批流程 |
| 条件 | 准入条件 |
| 范围 | 服务范围、担保范围 |
| 对象 | 服务对象 |
| 主体 | 经营主体、申保主体 |

这些都是业务方案的核心字段锚点，被丢弃后知识图谱中失去这些关键节点，`graph` 召回路径严重受损。

**建议处理**：

```python
# 改为 profile-aware 过滤，business_plan 不过滤上述词
PROFILE_GENERIC_FILTER = {
    "business_plan": set(),  # 不过滤
    "general_document": {"的", "是", ...},
    "default": GENERIC_ANCHOR_TEXTS,
}
```

---

#### #4 低置信度知识单元对检索完全不可见

**位置**：`mysql_store.py:1580`

**现象**：

```python
AUTO_ACCEPT_THRESHOLD = 0.65

if confidence >= AUTO_ACCEPT_THRESHOLD:
    # 存入 kb_anchor_registry / kb_knowledge_unit
else:
    # 只存 kb_knowledge_candidate_pool，不入正式表
```

**影响**：

- LLM 提取置信度 < 0.65 的 anchor / unit / relation 全部不可检索
- 阈值是全局硬编码的，无法按 profile 调整
- 候选池数据需要通过审核 UI 人工确认后才能生效，但 dev 环境通常没有审核流程
- 对于 `business_plan` 这类结构化文档，LLM 的 `confidence` 字段本身并不可靠

**建议处理**：

1. 对 `business_plan` 降低阈值到 0.4 或 0.5
2. 或者增加环境变量 `KNOWLEDGE_AUTO_ACCEPT_THRESHOLD` 可配置
3. 候选池增加自动晋升机制：规则提取的 anchor（`source="rule"`）直接接受

---

### 🟠 高优先级问题

#### #5 LLM 提取失败时维度数据被清空

**位置**：`extractor.py:673`

**现象**：

```python
if llm_ok:
    regions = llm_regions
    industries = llm_industries
    organizations = llm_organizations
else:
    regions = []       # 全空！
    industries = []    # 全空！
    organizations = [] # 全空！
```

**影响**：

- LLM 超时或报错时，地区/行业/组织维度全部丢失
- 规则提取阶段从来不填充这些维度，只能依赖 LLM
- 检索时的 scope anchor 过滤、region/industry 筛选全部失效

**建议处理**：

规则提取增加正则兜底：从 chunk 文本中匹配已知的地区名/行业名列表。

---

#### #6 QA 预生成中单条 evidence 失败导致整条 QA 丢弃

**位置**：`answer_prebuilder.py:118`

**现象**：

```python
# 只要有一个 evidence quote 对不上，整条 QA 丢弃
if not all(alignment for alignment in evidence_alignments):
    continue  # 丢弃整条 QA！
```

**影响**：

- LLM 生成的 QA 包含多个 evidence 引用时，只要一个对齐不上就全丢
- `max_pairs=30` 的上限进一步放大了这个问题，剩余 QA 数量更少

**建议处理**：

改为丢弃失败的 evidence 但保留 QA pair（标记为部分对齐），或至少保留对齐数 ≥50% 的 QA。

---

#### #7 字段提取中正则直接覆盖 LLM 结果无交叉校验

**位置**：`extractor.py:103, 679`

**现象**：

```python
DETERMINISTIC_FIELDS = ["credit_limit", "guarantee_rate", "loan_period", ...]

# 正则提取直接覆盖 LLM
for field_code in DETERMINISTIC_FIELDS:
    if field_code in regex_fields:
        merged[field_code] = regex_fields[field_code]  # LLM 结果被覆盖
```

**影响**：

- 正则误提取时（如"100万元"被错误识别为授信额度而非反担保金额），LLM 的正确结果被丢弃
- 没有交叉校验机制，不知道正则和 LLM 哪个更可信

**建议处理**：

当正则和 LLM 值差异 > 20% 时，保留两者并标记冲突，或优先保留与上下文更一致的值。

---

### 🟡 中优先级问题

#### #8 中文关键词匹配在混合语言文档上失效

**位置**：`catalog_chunker.py:1059`

`_classify_mapped_sections` 使用硬编码中文关键词做 section type 推断，英文文档章节无法正确分类。

**建议**：增加英文关键词映射表。

---

#### #9 摘要生成 LLM 异常被静默吞掉

**位置**：`section_builder.py:678`

```python
except Exception:
    pass  # LLM 超时、格式错误全部静默降级
```

**影响**：运维无法感知摘要质量下降。

**建议**：增加 warning 级别日志 + 计数统计。

---

#### #10 context chunk 被排除在跨 chunk 关系之外

**位置**：`mysql_store.py:1116`

```python
if chunk.get("chunk_type") == "small_chunk" or (chunk.get("metadata") or {}).get("retrieval_role") != "context":
    chunk_rows_for_relations.append(...)
```

`section_chunk` 和 `parent_chunk` 的 `retrieval_role="context"` 被排除，它们没有 `same_section_type`、`same_group` 等关系。

**影响**：context chunk 之间无法互相引用，限制了下游检索的图扩展能力。

**建议**：context chunk 也应该参与关系构建。

---

## 三、修复优先级建议

| 优先级 | 问题 | 影响面 | 修复难度 |
|--------|------|--------|---------|
| P0 | #1 父子层级断裂 | 检索上下文质量 | 低 ✅部分已修 |
| P0 | #2 目录失败全文档坍塌 | 整个解析失效 | 中 |
| P0 | #3 误杀核心锚点 | 图检索路径 | 低 |
| P1 | #4 低置信度知识不可见 | 知识图谱覆盖 | 低 |
| P1 | #5 LLM 失败维度丢失 | scope 过滤 | 中 |
| P1 | #6 单条 evidence 丢弃整条 QA | QA 召回 | 低 |
| P1 | #7 正则直接覆盖 LLM | 字段准确性 | 中 |
| P2 | #8-10 | 边缘场景 | 低-中 |

---

## 四、本次已修复项

| 日期 | 问题 | 变更 |
|------|------|------|
| 2026-06-22 | `child_context_by_key` 只从 `section_chunk` 构建 | `mysql_store.py:1158` — 扩展为 `{"section_chunk", "parent_chunk"}` |
| 2026-06-22 | KB 级别重建索引入口缺失 | `retrieve_service.py` — 新增 `POST /api/v1/index/kb/rebuild` |
| 2026-06-22 | 代理 thirdInterfaceId 写死 chat-completions | `openai_compat.py` — 支持 `EMBEDDING_PROXY_INTERFACE_ID` 环境变量 |
| 2026-06-22 | dev 环境华为云 CSS 适配 | `es_store.py` — CSS vector mapping / bulk write / vector query |
