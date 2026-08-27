# VisRAG 完整分析借鉴报告

> 分析对象：`D:\pyproject\bisheng\VisRAG-master`（OpenBMB/面壁智能，arXiv 2410.10594 + 2510.09733）
> 对照项目：danbao-poc（本仓库，多模态知识特性）
> 日期：2026-08-13

---

## 一、一句话定位

VisRAG 是**纯视觉的 RAG 管线**：不把文档解析成文字，而是把文档的**每一页直接渲染成图片**，用 VLM 把整页图**编码成单个向量**做检索，然后把命中的**原图**直接喂给 VLM 生成答案。核心主张是「**消除解析带来的信息损失**，最大化保留原文档信息」。

VisRAG 2.0（**EVisRAG**）在此基础上加了**证据引导的多图推理**：生成时先让 VLM「观察」每张图、逐图记录证据、标记无关图，再基于证据推理作答，并用 RS-GRPO 强化学习训练这个「观察→取证→推理」过程。

---

## 二、核心原理：单向量视觉嵌入（Single-Vector Visual Embedding）

VisRAG 的检索是**单向量 bi-encoder**（对比 ColPali 的多向量迟交互）：

```
文档页 → 渲染成图 → VLM(MiniCPM-V 2.0) → last_hidden_state
                                              │
                                     last_token_pool(取最后一个 token)
                                              │
                                      L2 normalize → 单个向量(表示整页)
                                              │
查询 → 同样编码 → 单个向量 → 点积打分
```

关键代码（`dense_retrieval_model.py`）：

```python
# 池化：取 last token 的隐状态作为整页表示（decoder-only 模型惯用）
def last_token_pool(last_hidden_states, attention_mask):
    ...
    return last_hidden_states[..., sequence_lengths]  # 每个样本取自己的最后一个有效 token

# 归一化
reps = F.normalize(reps, dim=1)
```

模型骨干（`modeling_visrag_ret.py`）：`VisRAG_Ret` 继承 MiniCPM-V 2.0（**SigLIP 视觉编码器 + MiniCPM-2B 语言模型**），前向时图文的 vision embedding 和 text embedding 融合后过 LLM，取 last token 池化。

**三种范式一句话对比**：

| 项目 | 检索表示 | 打分 |
|------|---------|------|
| RAG-Anything | 文字描述 → 文字 embedding | 文字向量点积 |
| **VisRAG** | **整页图 → 单向量** | 视觉向量点积 |
| ColPali | 整页图 → 每个 patch 一个向量 | MaxSim 迟交互 |

精度上 ColPali(多向量) > VisRAG(单向量)，成本/复杂度上 VisRAG 更低。

---

## 三、架构拆解

### 3.1 VisRAG-Ret（检索，单向量 bi-encoder）

- 骨干：MiniCPM-V 2.0（SigLIP 视觉 + MiniCPM-2B 语言）
- 池化：`last_token_pool`（decoder-only 取最后一个 token 隐状态）
- 训练：基于 openmatch（Tevatron 系的检索训练框架），对比学习 + 蒸馏 + LoRA

### 3.2 VisRAG-Gen（生成）

- 任意 VLM 均可（论文用 MiniCPM-V 2.0/2.6、GPT-4o）
- 输入：查询 + 检索到的**原图**（多图直接拼进 prompt）

### 3.3 EVisRAG（生成侧的「证据引导」—— 最值得关注）

`prompt.py` 的 `evidence_prompt_grpo` 是这份代码里**最有价值的东西**。它把生成拆成 4 个显式步骤，用 XML 标签结构化：

```
Step 1 <observe>   逐张观察图片，判断哪些图与问题相关
Step 2 <evidence>  逐图记录证据；无关图标记为 "[i]: no relevant information"
Step 3 <think>     基于证据逐步推理
Step 4 <answer>    只基于证据给最终答案（证据不足则答 "insufficient to answer"）
```

这个设计的精妙之处：
1. **强制逐图取证**：避免 VLM 拿到一堆图后"囫囵吞枣"或"只看第一张"
2. **显式标记无关图**：`[i]: no relevant information` 让模型主动排除干扰项（多图检索常混入弱相关图）
3. **证据与答案分离**：`<evidence>` 是"找到的事实"，`<answer>` 是"基于事实的结论"，可追溯
4. **训练时用 RS-GRPO**：对 `<evidence>` 和 `<answer>` 的 token 分别给细粒度奖励，联合优化"视觉感知"和"推理"

---

## 四、与你 danbao-poc 的关系：三个项目横向对比

| 维度 | RAG-Anything | VisRAG | ColPali |
|------|-------------|--------|---------|
| 范式 | caption-then-embed | 单向量视觉检索 | 多向量视觉检索 |
| 要不要 OCR/解析 | 要（VL 顺带） | **不要** | **不要** |
| 索引什么 | 文字描述 | 整页图单向量 | 页 patch 多向量 |
| 生成时喂什么 | 文字 + 图附件 | **原图** | **原图** |
| 精度(复杂文档) | 中 | 高 | 最高 |
| 成本 | 最低 | 中 | 最高 |
| 对你的截图场景 | ✅ 贴合 | ⚠️ 偏重 | ⚠️ 偏重 |
| 最值得抄的部分 | 多模态处理工程细节 | **证据引导生成 prompt** | 热力图 + 迟交互思想 |

**结论**：三个项目各占一个位置——
- **RAG-Anything** 告诉你「图片怎么变知识」（你已经在做的方向）
- **VisRAG** 告诉你「检索命中多张图后，VLM 该怎么组织答案」（生成侧，你还没做）
- **ColPali** 告诉你「视觉检索的精度上限」（远期储备）

对你当前截图场景，**检索侧用 RAG-Anything 的 caption 路线**就够，但 **VisRAG 的 EVisRAG 证据引导 prompt 是直接能抄、且立刻提升你生成质量的**——因为你的系统最终也是「检索到文字+图片 → 喂给 VLM 生成答案」。

---

## 五、值得借鉴的点（按优先级）

### ⭐⭐⭐ 1. EVisRAG 证据引导生成 prompt —— 最有价值，直接可抄

这是 VisRAG 对你**最有用**的东西。你的生成环节（检索到文字 chunk + 图片 file_id → 拼 prompt 给 VLM）完全可以套用它的 4 步结构：

```
<observe> 观察检索到的文字+图片，判断哪些与问题相关
<evidence> 逐条记录证据；无关项标记 no relevant information
<think> 基于证据推理
<answer> 只基于证据给答案，证据不足则明确说 insufficient
```

好处：你现在的检索结果可能混入「弱相关 chunk」（尤其多路融合后），EVisRAG 的「逐条取证 + 显式排除无关项」能显著减少答非所问。**这是纯 prompt 工程，不需要改模型、不需要训练，当天就能上线。**

### ⭐⭐ 2. 「检索结果直接喂原图」的生成范式

VisRAG 生成时喂的是**原图**，不是描述文字。你现在的方案是「文字 chunk + 图片 file_id 作附件返回」。如果你想让最终答案更准确（尤其涉及「图里的具体位置/颜色/布局」这类视觉细节的问题），可以让生成侧 VLM 也吃图片。但注意——这要求你的生成模型是 VLM（能读图），你的 `JsonChatClient` 目前是纯文本的，要扩展成支持 `image_url` 的 content（`call_qianfan_vlm_ocr` 已经有这个能力，可以复用）。

### ⭐⭐ 3. 单向量视觉嵌入作为「轻量视觉检索」的备选

如果你将来要上视觉检索、但又嫌 ColPali 的 3B 多向量太重，VisRAG 的单向量是**中间档**：整页图 → 一个向量，存储/检索成本接近传统向量检索，精度高于文字检索（对图表类文档）。可以用 SigLIP 或现成 `VisRAG-Ret`。

### ⭐ 4. last_token_pool 池化技巧

decoder-only VLM 做嵌入时，用「最后一个有效 token 的隐状态」作为整段表示，这是因果模型的惯用池化。你如果将来用 Qwen-VL 这类 decoder-only 模型做嵌入，直接照搬。

### ⭐ 5. 「标记无关项」的多图抗噪机制

多图/多 chunk 检索时，主动让模型输出「这一项无关」比「让模型自己默默忽略」更可靠。这个思想不仅适用于图片，也适用于你的文字多路融合结果。

---

## 六、不建议借鉴的点

1. **整套 openmatch 检索训练框架** —— 你要用现成的 `VisRAG-Ret`/SigLIP 就行，不用自己训
2. **RS-GRPO 强化学习训练**（`rsgrpo/`、`verl/`） —— 这是 EVisRAG 的模型训练部分，需要 GPU 集群 + 强化学习栈，对你太重。你要抄的是它训出来的**prompt 结构**，不是它的训练过程
3. **MiniCPM-V 特定模型层**（`modeling_minicpmv/`、`modeling_siglip/`） —— 模型细节，跟你的 caption 路线无关

---

## 七、三个项目的最终落地建议（融合版）

结合 RAG-Anything + ColPali + VisRAG 三个分析，给你一条完整路线：

### 现在（caption-then-embed 落地，借 RAG-Anything + VisRAG）

1. **检索侧（存）**：docx 提图 → ContextExtractor 取邻居文字 → VL 生成描述（结构化 JSON）→ image_chunk 模板（标题+邻居+描述）→ 存 chunk + 图片 file_id
2. **生成侧（答）**：检索命中后，**用 EVisRAG 的 4 步证据引导 prompt** 组织 VLM 生成（`observe→evidence→think→answer`），无关 chunk 显式标记
3. **鲁棒性**：借 RAG-Anything 的 JSON 降级解析 + think 标签剥离

### 中期（可选，文字检索精度不够时）

4. 引入**文字版 ColBERT 迟交互**，替代/增强现有单向量 `vector` 模式

### 远期（按需，出现复杂 PDF 时）

5. 引入**视觉检索**作为第 5 种检索模式：单向量用 VisRAG-Ret/SigLIP（轻），多向量用 ColQwen2（精），返回原图 + ColPali 相似度热力图

---

## 八、总结

| 项目 | 核心贡献 | 你该抄什么 |
|------|---------|-----------|
| RAG-Anything | 多模态处理的工程细节 | 上下文感知、chunk 模板、JSON 降级解析 |
| **VisRAG** | 视觉检索 + **证据引导生成** | **EVisRAG 4 步 prompt**、检索喂原图、无关项标记 |
| ColPali | 多向量迟交互视觉检索 | 热力图 evidence、迟交互思想、效率技巧 |

**一句话结论**：VisRAG 对你最大的价值不在检索（你的 caption 路线够用），而在**生成侧的「证据引导」prompt**——这是三份代码里唯一一个「不改架构、不改模型、纯 prompt 就能显著提升答案质量」的拿来即用项，强烈建议先抄这个。
