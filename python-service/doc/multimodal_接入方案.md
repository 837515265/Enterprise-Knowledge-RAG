# danbao-poc 多模态知识 · 接入方案（可执行）

> 目标：把 LightRAG 的「docx 提图 + 上下文 VLM 描述」两小块能力移植进 danbao-poc 的解析层，视觉知识复用你现有的 chunk → 抽取 → 图 → MySQL/ES → 检索全链路。
> 结论：**不是新 Profile，不是整体复用 LightRAG，是「能力移植」**——`parse_options.multimodal` 开关，正交于 Profile。
> 日期：2026-08-19

---

## 0. 策略一句话

- **提图**（LightRAG `drawing_image_extractor.py`）→ 补进 `document_parser.py::_parse_docx`（现在丢图）。
- **VLM 描述**（LightRAG `analyze_multimodal` + `multimodal_context.py` 的「上下文 + 描述」模式）→ 新增 `multimodal.py`，复用你已有的 `call_qianfan_vlm_ocr`。
- **视觉 → chunk**（`chunk_type="image"`）→ 插进 `_parse_and_save`，之后**完全走你现有 pipeline**，零检索改动。

不新增 Profile；不引入 LightRAG 的存储/检索（JSON/NetworkX/NanoVectorDB 比你 MySQL/ES/Neo4j 弱）。

---

## 1. 总体接入点（对应 parse_service.py 的 `_parse_and_save`）

```
parse_document(file_name, file_bytes, ...)      # 改动点①：_parse_docx 提图 → middle_document["images"]
        ↓
analyze_images(middle_document, parse_options)  # 改动点②：新增 multimodal.py，VLM 描述 → visual_chunks
        ↓
catalog_builder(middle_document, ...)           # 现有：文字 chunk
        ↓
chunks = text_chunks + visual_chunks            # 改动点③：合并（视觉 chunk 是文字 chunk 的"同侪"）
        ↓
spec.extractor / extract_knowledge_structure / spec.graph_builder   # 现有，不动
        ↓
save_parse_result → MySQL kb_chunk → ES → 检索                          # 现有，不动
```

---

## 2. 改动点① · 提图（document_parser.py::_parse_docx）

### 现状（document_parser.py:250）

```python
def _parse_docx(file_name, file_bytes, document_id, profile):
    from docx import Document
    document = Document(BytesIO(file_bytes))
    paragraphs = [clean_text(p.text) for p in document.paragraphs ...]   # 只提文字
    # 图片被丢弃
```

### 移植要点（从 LightRAG `parser/docx/drawing_image_extractor.py`）

该文件约 400 行，**无重依赖**（`zipfile` + `lxml`/`xml.etree`），核心三个函数直接移植：

| LightRAG 函数 | 作用 | 移植后放哪 |
|---|---|---|
| `load_relationships()` | `zipfile` 读 `[Content_Types].xml` + `word/_rels/document.xml.rels`，重建 `rel_id → {part_name, format}` | 新增 `danbao_poc/docx_image_extractor.py` |
| `extract_drawing_placeholder_from_element()` | 从 `a:blip` 的 `r:embed` 取图；`r:link` 只记远程 URL | 同上 |
| `extract_vml_image_placeholder_from_element()` | 处理 `w:pict`/`w:object`（VML 旧格式 / EMF/WMF/OLE）——矢量图兜底 | 同上 |

注意 LightRAG **没用 python-docx 的 `related_parts`**，而是直接 `zipfile` 读关系表（等价职责，但可控性更好、能处理 VML 占位图）。移植时保留这个做法。

### 产出：填 `middle_document["images"]`

字段**已在 `_normalize_native_pages` 预留**（document_parser.py:216 的 `"images": []`），每张图一条：

```python
{
    "image_id": "img_p3_0001",              # 稳定 id
    "page_no": 3,
    "block_id": "p3_b004",                  # 所在 block
    "bbox": [x0, y0, x1, y1],
    "format": "png",                        # 或 jpeg（EMF/WMF 占位图跳过）
    "file_center_file_id": "xxx",           # 图字节 → FileCenterClient.upload_file
    "src": "",                              # 远程 URL（r:link 时，不下载）
    "surrounding_leading": "...",           # 图前文字（见改动点②）
    "surrounding_trailing": "...",          # 图后文字
}
```

关键点：
- 图字节**不要塞进 middle_document**，而是立刻 `FileCenterClient.upload_file(file_name=f"{file_name}.img{seq}.png", file_bytes=...)` 拿 `file_id`，middle_document 只存 file_id（对应你「图片独立存文件中心」的原则）。
- 同时把图所在 block 的 `type` 标成 `"image"`（`_normalize_native_pages` 的 block 已带 type/bbox/order，直接复用）。

---

## 3. 改动点② · 新增 `multimodal.py`（VLM 描述）

### 接口签名

```python
# danbao_poc/multimodal.py
from __future__ import annotations
from typing import Any

def analyze_images(
    middle_document: dict[str, Any],
    *,
    parse_options: dict[str, Any] | None,
    profile: str,
    file_center: "FileCenterClient",
    request_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """对 middle_document["images"] 每张图做「上下文感知 VLM 描述」。

    Returns:
        visual_chunks: 每张图一个 chunk(dict)，可直接并入 chunks 走 catalog/extract/storage。
        visual_assets:  每张图的原始元信息（落 file_visual_asset 表用）。
    """
```

### 内部三步（对应 LightRAG `analyze_multimodal`）

**1. 上下文感知**（借 `multimodal_context.py` 的 `build_surrounding` 思路）：取图片所在 block 前后 N 个文字 block，拼进 prompt，让描述带上业务语境（「自然人微信支付 / 企业转账支付」步骤文字），而不是孤立描述「一个界面」。

**2. 调 VLM**（复用你已有的后端，不新造）：

```python
from danbao_poc.model_router import ModelRouter
from danbao_poc.ocr_client import call_qianfan_vlm_ocr

route = ModelRouter().select("VISION")   # 新增 VISION 前缀，配置 VISION_PRIMARY_MODEL_NAME=qwen3-vl-32b-think 等
result = call_qianfan_vlm_ocr(
    base_url=route.base_url,
    model=route.model_name,
    api_key=route.api_key,
    image_bytes=image_bytes,
    image_mime_type=f"image/{fmt}",
    prompt=_build_vision_prompt(visual_type_hint, leading, trailing, profile),
)
```

`_build_vision_prompt` 要求 VLM 返回结构化 JSON：`{name, type, description}`，type 限枚举 `["Screenshot","Chart","Flowchart","Architecture","GeneralImage","Other"]`。

**3. 鲁棒 JSON 解析**（借 LightRAG `_validate_drawing_analysis` + RAG-Anything `_robust_json_parse`）：你现有 `openai_compat.JsonChatClient.complete_json` 直接 `json.loads`，VLM 吐 `<think>`/markdown 代码块就炸，这里补多级降级 + think 剥离。

### visual_chunk 结构（可直接进你现有 chunk 体系）

```python
{
    "chunk_key": f"img_p{page_no}_{seq:03d}",
    "seq_no": seq_no,
    "chunk_type": _chunk_type_for(visual_type),   # image / chart / diagram / ui_screenshot
    "section_type": "image",
    "section_id": f"img:{image_id}",
    "chunk_group_id": f"img:{image_id}",
    "title": visual["name"],                       # 「保费缴纳页面截图」
    "title_path": [document_title, visual["name"]],
    "content": visual["description"],              # searchable 文本，就是 VLM 描述
    "summary": visual["description"][:180],
    "content_hash": stable_hash(visual["description"], 40),
    "content_for_embedding": _embedding_text(document_title, visual["name"], visual["description"]),
    "content_for_bm25": f"{document_title} {visual['name']} {visual['description']}",
    "page_start": page_no, "page_end": page_no,
    "block_ids": [image["block_id"]],
    "bbox": [image["bbox"]],
    "metadata": {
        "visual_type": visual["type"],             # Screenshot / Chart / ...
        "file_center_file_id": image["file_center_file_id"],
        "visual_asset_id": image["image_id"],
        "profile": profile,
        "vlm_model": route.model_name,
        "confidence": "HIGH",
    },
}
```

> 这套字段与 `registry.py::_clone_chunk_with_content` / `_chunk_structured_data` 的 chunk 完全同构，`chunk_type` 复用现有机制，**不需要新列**。

---

## 4. 改动点③ · 插入位置（parse_service.py::_parse_and_save）

### 精确插入（在 line 785 `parse_document` 之后、line 813 `catalog_builder` 之前）

```python
# ... line 778-785: middle_document, raw_payload = parse_document(...)

# ── 新增：多模态分析 ─────────────────────────────────────────
visual_chunks: list[dict[str, Any]] = []
visual_assets: list[dict[str, Any]] = []
if (parse_options or {}).get("multimodal", {}).get("enabled") and middle_document.get("images"):
    if task_id:
        update_parse_task(task_id, stage="multimodal_analyzing")
        _parse_log("parse task multimodal_analyzing task_id=%s images=%s", task_id, len(middle_document.get("images")))
    visual_chunks, visual_assets = analyze_images(
        middle_document,
        parse_options=parse_options,
        profile=profile,
        file_center=FileCenterClient(),
        request_id=request_id,
    )
    _write_process_artifact(process_dir, "02_multimodal.json", {"visual_chunks": visual_chunks, "visual_assets": visual_assets})
# ─────────────────────────────────────────────────────────────

# ... line 813-826: catalog_builder → chunks
chunks = catalog_result.chunks + visual_chunks      # ← 合并（视觉 chunk 追加在文字 chunk 之后）
```

### 说明

- `visual_chunks` 是文字 chunk 的**同侪**，`seq_no` 从文字 chunk 之后续接（`save_parse_result` 里已有按 `seq_no` 排序，无需特殊处理）。
- 后续 `spec.extractor(primary_chunks)`、`extract_knowledge_structure(chunks)`、`spec.graph_builder(extraction)` **全部不动**——视觉 chunk 的 VLM 描述文本会被自然抽成字段/anchor/unit/relation（例如「转账账户=招商银行资金清算部」），进入你现有 `kb_anchor_registry` + 图，**比 LightRAG 单造 `im-xxx` 实体更统一**。
- 若要保留「图片本身是证据单元」语义，在 `extract_knowledge_structure` 里对 `chunk_type="image"` 的 chunk 额外产一个 `anchor_type="visual_asset"` 的 anchor，metadata 带 `file_center_file_id`（供检索端回看原图）。

---

## 5. 存储改动

### 5.1 kb_chunk：复用，不加列

- `chunk_type VARCHAR(32)` 已有（mysql_store.py:174）→ 用新值 `image` / `chart` / `diagram` / `ui_screenshot`。
- 视觉元信息进 `metadata_json JSON`（mysql_store.py:181），不进新列。

### 5.2 新增两张 `file_*` 表（遵循你 `file_tables`/`file_char_map` 命名约定）

```sql
-- 原图资源（图片本身，存文件中心 file_id）
CREATE TABLE IF NOT EXISTS file_visual_asset (
  id BIGINT PRIMARY KEY,
  kb_id BIGINT NOT NULL,
  file_node_id BIGINT NOT NULL,
  parse_generation VARCHAR(128) DEFAULT NULL,
  image_id VARCHAR(64) NOT NULL,
  file_center_file_id VARCHAR(128) DEFAULT NULL,
  page_no INT DEFAULT NULL,
  block_id VARCHAR(64) DEFAULT NULL,
  bbox_json JSON DEFAULT NULL,
  section_id VARCHAR(128) DEFAULT NULL,
  visual_type VARCHAR(32) DEFAULT NULL,
  image_format VARCHAR(16) DEFAULT NULL,
  del_flag TINYINT NOT NULL DEFAULT 0,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_visual_file (kb_id, file_node_id, parse_generation),
  UNIQUE KEY uk_visual_image (kb_id, file_node_id, image_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VL 分析结果（AI 理解出的内容）
CREATE TABLE IF NOT EXISTS file_visual_analysis (
  id BIGINT PRIMARY KEY,
  kb_id BIGINT NOT NULL,
  visual_asset_id BIGINT NOT NULL,
  image_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) DEFAULT NULL,
  visual_type VARCHAR(32) DEFAULT NULL,
  description LONGTEXT,
  structured_json JSON DEFAULT NULL,
  searchable_text LONGTEXT,
  vlm_model VARCHAR(128) DEFAULT NULL,
  prompt_version VARCHAR(32) DEFAULT NULL,
  confidence VARCHAR(16) DEFAULT NULL,
  del_flag TINYINT NOT NULL DEFAULT 0,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_visual_analysis_file (kb_id, visual_asset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

落库：`save_parse_result` 里仿照 `file_tables`/`file_table_rows` 的写法，把 `visual_assets` 写 `file_visual_asset`、`visual_chunks` 的 metadata 写 `file_visual_analysis`（检索文本进 `kb_chunk`）。

---

## 6. 检索端：零改动 + 一处可选增强

- **零改动**：视觉 chunk 的 `content`（VLM 描述）填了 `content_for_bm25` + `content_for_embedding`，自动进 ES 的 bm25 + vector 索引，靠现有 6 路检索命中（和 `table_schema` 等 chunk 完全一致）。
- **可选增强**：检索命中 `chunk_type="image"` 的 chunk 后，在 EvidenceGroup 里挂 `visual_evidence`（含 `file_center_file_id` + VLM 描述），上层可渲染原图。对应改动在 retrieve_service 的 evidence 组装处（`answer_context_protocol.py`），首版可不做。

---

## 7. 开关与灰度

```json
"parse_options": { "multimodal": { "enabled": true } }
```

- `enabled=false` 或不传 → 走现有行为，**零回归**。
- `_parse_cache_identity`（parse_service.py:664）已把 `parse_options` 纳入 hash，开关变化会自动失效缓存，无需额外处理。

---

## 8. 从 LightRAG 抄的清单（不抄整体）

| 抄什么 | LightRAG 文件 | 抄进 danbao-poc |
|---|---|---|
| docx 提图（zipfile 读 rels + blip/VML） | `parser/docx/drawing_image_extractor.py` | 新增 `docx_image_extractor.py` |
| 上下文回填（leading/trailing） | `multimodal_context.py::build_surrounding` | `multimodal.py` 内联 |
| VLM 描述 + JSON 校验/重试 | `pipeline.py::_analyze_drawing` / `_validate_drawing_analysis` | `multimodal.py` 内联 |
| 鲁棒 JSON 解析 + think 剥离 | RAG-Anything `_robust_json_parse` | 补进 `openai_compat.py` |

**不抄**：LightRAG 的存储（NetworkX/NanoVectorDB/JsonKV）、检索（kg_query）、图实体注入（im-xxx 合成节点）、服务层（lightrag-server）。

---

## 9. 实施顺序（可分批灰度）

1. **P0 · 提图**：`docx_image_extractor.py` + `_parse_docx` 提图 + 图字节进文件中心。验证 `middle_document["images"]` 有内容。
2. **P1 · VLM 描述**：`multimodal.py` + `ModelRouter` 加 `VISION` 前缀 + `_parse_and_save` 插入。验证 `visual_chunks` 生成。
3. **P2 · 存储**：两张新表 + `save_parse_result` 落库 + 视觉 chunk 进 kb_chunk/ES。验证能检索到图片内容。
4. **P3 · 检索增强**：EvidenceGroup 挂 `visual_evidence`（回看原图），可选。

---

## 10. 风险与回滚

- 全链路在 `parse_options.multimodal.enabled` 门后，关闭即回滚。
- VLM 是新增外部调用（成本/延迟），首版建议 `max_images_per_doc` 上限 + 失败降级（VLM 失败不阻塞解析，只跳过该图）。
- 视觉 chunk 进入抽取会多消耗 LLM 抽取额度，可复用 `sql_analytics` 的 `enable_knowledge_extraction=False` 思路，为视觉 chunk 单独控制是否进抽取。
