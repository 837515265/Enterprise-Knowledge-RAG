const $ = (id) => document.getElementById(id);
let lastParseResult = null;

function setStatus(message, type = "") {
  const el = $("status");
  el.textContent = message;
  el.className = `status ${type}`;
}

function show(data) {
  renderRetrieveInsights(data);
  $("output").textContent = JSON.stringify(data, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function shortText(value, max = 180) {
  const text = String(value ?? "").trim();
  return text.length > max ? `${text.slice(0, max - 1).trim()}...` : text;
}

function renderRetrieveInsights(data) {
  const panel = $("retrieveInsights");
  const groups = Array.isArray(data?.evidence_groups) ? data.evidence_groups : [];
  const references = Array.isArray(data?.references) ? data.references : Array.isArray(data?.citations) ? data.citations : [];
  const answerContext = data?.answer_context || {};
  if (!groups.length && !references.length && !answerContext.prompt_context) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  $("confidenceValue").textContent = `${data.confidence_label || "-"} ${data.confidence ?? ""}`.trim();
  const routeReason = data?.debug?.route_reason || data?.retrieval_plan?.route_reason || {};
  const routeEntries = Object.entries(routeReason);
  $("routeBadges").innerHTML = routeEntries.length
    ? routeEntries.map(([route, reason]) => `<span class="badge" title="${escapeHtml(reason)}">${escapeHtml(route)}</span>`).join("")
    : `<span class="badge">未返回路由原因</span>`;

  $("evidenceList").innerHTML = groups.slice(0, 8).map((item, index) => {
    const title = item.title || item.field_name_cn || item.doc_name || `证据 ${index + 1}`;
    const route = item.route || item.match_type || item.hit_type || "";
    const score = item.final_score ?? item.score ?? "";
    const text = item.answer_hint || item.display_text || item.evidence_text || item.content || "";
    const chain = Array.isArray(item.evidence_chain) ? item.evidence_chain.join(" > ") : "";
    return `
      <article class="evidence-item">
        <div class="item-title">
          <span>${escapeHtml(title)}</span>
          <span class="item-meta">${escapeHtml(route)} ${escapeHtml(score)}</span>
        </div>
        <div class="item-text">${escapeHtml(shortText(text))}</div>
        ${chain ? `<div class="item-meta">${escapeHtml(chain)}</div>` : ""}
      </article>
    `;
  }).join("");

  const blocksByRef = new Map((answerContext.blocks || []).map((block) => [block.ref_id, block]));
  $("referenceList").innerHTML = references.slice(0, 8).map((item) => {
    const block = blocksByRef.get(item.citation_id) || {};
    return `
      <article class="reference-item">
        <div class="item-title">
          <span>${escapeHtml(item.citation_id || block.ref_id || "ref")}</span>
          <span class="item-meta">${escapeHtml(item.meta || "")}</span>
        </div>
        <div class="item-text">${escapeHtml(shortText(block.quote || item.content))}</div>
      </article>
    `;
  }).join("");
  $("answerPrompt").textContent = answerContext.prompt_context || data.answer_context_prompt || "";
}

async function requestJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.data = data;
    throw error;
  }
  return data;
}

$("healthBtn").addEventListener("click", async () => {
  setStatus("正在检查服务...");
  try {
    const [gateway, business, parse, retrieve, infra] = await Promise.all([
      fetch("/health").then((r) => r.text()),
      fetch("/business/health").then((r) => r.json()),
      fetch("/parse/health").then((r) => r.json()),
      fetch("/retrieve/health").then((r) => r.json()),
      fetch("/business/api/v1/infra/health").then((r) => r.json()),
    ]);
    setStatus("服务正常", "ok");
    show({ gateway: gateway.trim(), business, parse, retrieve, infra });
  } catch (error) {
    setStatus("服务检查失败", "bad");
    show({ message: error.message, data: error.data || null });
  }
});

$("parseBtn").addEventListener("click", async () => {
  const documentId = $("docId").value.trim();
  const file = $("pdfFile").files[0];
  if (!file) {
    setStatus("请选择 PDF 文件", "bad");
    return;
  }
  setStatus("正在上传、解析并写入业务库...");
  $("parseBtn").disabled = true;
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("knowledge_base_id", $("kbId").value.trim());
    form.append("document_id", documentId);
    form.append("profile", $("profile").value.trim());
    const response = await fetch("/business/api/v1/upload-parse", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status}`), { data });
    lastParseResult = data;
    if (data.document_id) $("docId").value = data.document_id;
    if (data.file_name) $("fileName").value = data.file_name;
    setStatus("解析并入库完成", "ok");
    show(data);
  } catch (error) {
    setStatus("上传解析失败", "bad");
    show({ message: error.message, data: error.data || null });
  } finally {
    $("parseBtn").disabled = false;
  }
});

$("listBtn").addEventListener("click", async () => {
  setStatus("正在读取业务库文档...");
  try {
    const response = await fetch(`/business/api/v1/documents?knowledge_base_id=${encodeURIComponent($("kbId").value.trim())}`);
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status}`), { data });
    setStatus("文档列表读取完成", "ok");
    show(data);
  } catch (error) {
    setStatus("读取文档列表失败", "bad");
    show({ message: error.message, data: error.data || null });
  }
});

$("indexBtn").addEventListener("click", async () => {
  if (!$("docId").value.trim()) {
    setStatus("请先填写或上传生成文档 ID", "bad");
    return;
  }
  setStatus("正在导入 Neo4j...");
  $("indexBtn").disabled = true;
  try {
    const data = await requestJson("/business/api/v1/sync-graph", {
      knowledge_base_id: $("kbId").value.trim(),
      document_id: $("docId").value.trim(),
      document_name: $("fileName").value.trim(),
    });
    setStatus("图谱导入完成", "ok");
    show(data);
  } catch (error) {
    setStatus("图谱导入失败", "bad");
    show({ message: error.message, data: error.data || null });
  } finally {
    $("indexBtn").disabled = false;
  }
});

$("pdfFile").addEventListener("change", () => {
  const file = $("pdfFile").files[0];
  if (file) $("fileName").value = file.name;
});

$("retrieveBtn").addEventListener("click", async () => {
  setStatus("正在检索...");
  $("retrieveBtn").disabled = true;
  try {
    const data = await requestJson("/business/api/v1/query", {
      knowledge_base_id: $("kbId").value.trim(),
      query: $("query").value.trim(),
      document_ids: $("docId").value.trim() ? [$("docId").value.trim()] : [],
      top_k: Number($("topK").value || 5),
    });
    setStatus("检索完成", "ok");
    show(data);
  } catch (error) {
    setStatus("检索失败", "bad");
    show({ message: error.message, data: error.data || null });
  } finally {
    $("retrieveBtn").disabled = false;
  }
});
