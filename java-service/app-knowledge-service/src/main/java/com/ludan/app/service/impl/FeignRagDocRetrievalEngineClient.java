package com.ludan.app.service.impl;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.config.RetrievalEngineProperties;
import com.ludan.app.dto.rag.RagIndexChunksRequest;
import com.ludan.app.dto.rag.RagIndexChunksResponse;
import com.ludan.app.dto.rag.RagIndexFileRequest;
import com.ludan.app.dto.rag.RagIndexFileResponse;
import com.ludan.app.dto.rag.RagIndexKbQasRequest;
import com.ludan.app.dto.rag.RagIndexKbQasResponse;
import com.ludan.app.dto.rag.RagIndexKbRebuildRequest;
import com.ludan.app.dto.rag.RagIndexQasRequest;
import com.ludan.app.dto.rag.RagIndexQasResponse;
import com.ludan.app.dto.rag.RagRetrieveQueryRequest;
import com.ludan.app.dto.rag.RagRetrieveQueryResponse;
import com.ludan.app.dto.rag.RagRetrieveResultItem;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.feign.AppRagDocRetrieveClient;
import com.ludan.app.service.RetrievalEngineClient;
import com.ludan.app.service.model.RetrievalEngineHit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.util.CollectionUtils;

import javax.annotation.PostConstruct;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 通过 OpenFeign 调用 {@code app-rag-doc}，实现《当前代码接口完整文档》混合检索。
 *
 * @author ludan
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class FeignRagDocRetrievalEngineClient implements RetrievalEngineClient {

    private final AppRagDocRetrieveClient ragDocRetrieveClient;
    private final RetrievalEngineProperties properties;
    private final ObjectMapper objectMapper;

    @PostConstruct
    public void init() {
        log.info("检索客户端(Feign): name=app-rag-doc, enabled={}, profile={}, compatPath={}",
                properties.isEnabled(), properties.getDefaultProfile(), properties.isCompatRetrievePath());
    }

    @Override
    public Map<String, Object> getKnowledgeBaseGraph(Long kbId, boolean includeChunks) {
        if (!properties.isEnabled()) {
            throw new RuntimeException("检索引擎未启用");
        }
        if (kbId == null) {
            throw new RuntimeException("知识库ID不能为空");
        }
        try {
            return ragDocRetrieveClient.getKnowledgeBaseGraph(kbId, includeChunks);
        } catch (Exception e) {
            log.error("app-rag-doc 知识库图谱读取失败: kbId={}, error={}", kbId, e.getMessage(), e);
            throw new RuntimeException("图谱服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> getFileGraph(Long kbId, Long fileNodeId, boolean includeChunks) {
        if (!properties.isEnabled()) {
            throw new RuntimeException("检索引擎未启用");
        }
        if (kbId == null || fileNodeId == null) {
            throw new RuntimeException("知识库ID和文件ID不能为空");
        }
        try {
            return ragDocRetrieveClient.getFileGraph(fileNodeId, kbId, includeChunks);
        } catch (Exception e) {
            log.error("app-rag-doc 图谱读取失败: kbId={}, fileNodeId={}, error={}", kbId, fileNodeId, e.getMessage(), e);
            throw new RuntimeException("图谱服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> getKnowledgeBaseGraphAudit(Long kbId, int hubDegree, int limit) {
        if (!properties.isEnabled() || kbId == null) {
            throw new RuntimeException(kbId == null ? "知识库ID不能为空" : "检索引擎未启用");
        }
        try {
            return ragDocRetrieveClient.getKnowledgeBaseGraphAudit(kbId, hubDegree, limit);
        } catch (Exception e) {
            log.error("app-rag-doc 图谱体检失败: kbId={}, error={}", kbId, e.getMessage(), e);
            throw new RuntimeException("图谱体检服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public Map<String, Object> rebuildKnowledgeBaseGraphCommunities(Long kbId, int minSize) {
        if (!properties.isEnabled() || kbId == null) {
            throw new RuntimeException(kbId == null ? "知识库ID不能为空" : "检索引擎未启用");
        }
        try {
            return ragDocRetrieveClient.rebuildKnowledgeBaseGraphCommunities(kbId, minSize);
        } catch (Exception e) {
            log.error("app-rag-doc 社区重建失败: kbId={}, error={}", kbId, e.getMessage(), e);
            throw new RuntimeException("图谱社区重建调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public List<RetrievalEngineHit> retrieveForKnowledgeBases(List<Long> kbIds, String query, int topK,
                                                               Map<String, Object> customOptions) {
        return doRetrieve(kbIds, query, topK, customOptions);
    }

    /**
     * 公共检索实现：统一使用 kb_ids 多库接口。
     */
    private List<RetrievalEngineHit> doRetrieve(List<Long> kbIds, String query, int topK,
                                                 Map<String, Object> customOptions) {
        if (!properties.isEnabled()) {
            return new ArrayList<>();
        }
        if (CollectionUtils.isEmpty(kbIds)) {
            return new ArrayList<>();
        }
        if (query == null || query.trim().isEmpty()) {
            return new ArrayList<>();
        }

        RagRetrieveQueryRequest req = new RagRetrieveQueryRequest();
        req.setKbIds(kbIds);
        req.setQuery(query.trim());
        req.setTopK(topK > 0 ? topK : 5);
        Map<String, Object> options = new HashMap<>(4);
        if (customOptions != null && !customOptions.isEmpty()) {
            options.putAll(customOptions);
        }
        applyFileNodeScope(req, options);
        // 不再向 rag-doc 传递 profile
        options.remove("profile");
        if (!options.isEmpty()) {
            req.setOptions(options);
        }

        try {
            RagRetrieveQueryResponse resp = properties.isCompatRetrievePath()
                    ? ragDocRetrieveClient.retrieveCompat(req)
                    : ragDocRetrieveClient.retrieveQuery(req);
            if (resp == null || CollectionUtils.isEmpty(resp.getResults())) {
                return new ArrayList<>();
            }
            List<RetrievalEngineHit> out = new ArrayList<>(resp.getResults().size());
            for (RagRetrieveResultItem it : resp.getResults()) {
                out.add(toHit(it));
            }
            return out;
        } catch (Exception e) {
            log.error("app-rag-doc 检索失败: kbIds={}, error={}", kbIds, e.getMessage(), e);
            throw new RuntimeException("检索服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String retrieveLlmContext(List<Long> kbIds, String query, Integer topK,
                                      Map<String, Object> customOptions) {
        if (!properties.isEnabled()) {
            return "";
        }
        if (CollectionUtils.isEmpty(kbIds)) {
            return "";
        }
        if (query == null || query.trim().isEmpty()) {
            return "";
        }

        RagRetrieveQueryRequest req = new RagRetrieveQueryRequest();
        req.setKbIds(kbIds);
        req.setQuery(query.trim());
        req.setTopK(topK != null && topK > 0 ? topK : 5);
        Map<String, Object> options = new HashMap<>(4);
        if (customOptions != null && !customOptions.isEmpty()) {
            options.putAll(customOptions);
        }
        applyFileNodeScope(req, options);
        options.remove("profile");
        if (!options.isEmpty()) {
            req.setOptions(options);
        }

        try {
            RagRetrieveQueryResponse resp = properties.isCompatRetrievePath()
                    ? ragDocRetrieveClient.retrieveCompat(req)
                    : ragDocRetrieveClient.retrieveQuery(req);
            return resp == null || resp.getLlmContext() == null ? "" : resp.getLlmContext();
        } catch (Exception e) {
            log.error("app-rag-doc llm_context 获取失败: kbIds={}, error={}", kbIds, e.getMessage(), e);
            throw new RuntimeException("LLM上下文获取失败: " + e.getMessage(), e);
        }
    }

    private void applyFileNodeScope(RagRetrieveQueryRequest req, Map<String, Object> options) {
        Object fileNodeIds = options.remove("fileNodeIds");
        if (!(fileNodeIds instanceof List)) {
            return;
        }
        List<Long> nodeIds = new ArrayList<>();
        for (Object nodeId : (List<?>) fileNodeIds) {
            nodeIds.add(Long.valueOf(nodeId.toString()));
        }
        req.setFileNodeIds(nodeIds);
    }

    @Override
    public String rebuildFileIndex(KbFileTask task) {
        if (!properties.isEnabled()) {
            throw new RuntimeException("检索引擎未启用");
        }
        if (task == null || task.getKbId() == null || task.getFileNodeId() == null) {
            throw new RuntimeException("文件索引参数不完整");
        }
        RagIndexFileRequest req = new RagIndexFileRequest();
        req.setKbId(task.getKbId());
        req.setFileNodeId(task.getFileNodeId());
        req.setParseGeneration(task.getParseGeneration());
        req.setIndexGeneration(task.getIndexGeneration());
        req.setOperation("rebuild");
        req.setAsyncMode(properties.isIndexAsyncMode());
        try {
            RagIndexFileResponse resp = ragDocRetrieveClient.rebuildFileIndex(req);
            validateIndexResponse(resp, "文件索引");
            return resp.getTaskId();
        } catch (Exception e) {
            log.error("app-rag-doc 文件索引失败: taskId={}, kbId={}, fileNodeId={}, error={}",
                    task.getId(), task.getKbId(), task.getFileNodeId(), e.getMessage(), e);
            throw new RuntimeException("索引服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String rebuildKbIndex(Long kbId) {
        if (!properties.isEnabled()) {
            throw new RuntimeException("检索引擎未启用");
        }
        if (kbId == null) {
            throw new RuntimeException("知识库ID不能为空");
        }
        RagIndexKbRebuildRequest req = new RagIndexKbRebuildRequest();
        req.setKbId(kbId);
        try {
            RagIndexFileResponse resp = ragDocRetrieveClient.rebuildKbIndex(req);
            validateIndexResponse(resp, "知识库索引");
            log.info("KB 级索引重建已提交: kbId={}, status={}", kbId, resp.getStatus());
            return resp.getTaskId();
        } catch (Exception e) {
            log.error("app-rag-doc KB 索引重建失败: kbId={}, error={}", kbId, e.getMessage(), e);
            throw new RuntimeException("索引服务调用失败: " + e.getMessage(), e);
        }
    }

    private void validateIndexResponse(RagIndexFileResponse response, String operationName) {
        if (response == null || response.getStatus() == null) {
            throw new RuntimeException(operationName + "服务返回空响应");
        }
        String status = response.getStatus().trim().toLowerCase();
        if (!"accepted".equals(status) && !"success".equals(status) && !"succeeded".equals(status)) {
            throw new RuntimeException(operationName + "服务未接受任务: status=" + response.getStatus());
        }
        if ("accepted".equals(status)
                && (response.getTaskId() == null || response.getTaskId().trim().isEmpty())) {
            throw new RuntimeException(operationName + "服务未返回任务ID");
        }
    }

    @Override
    public String rebuildQaIndex(Long kbId) {
        if (!properties.isEnabled() || kbId == null) {
            return null;
        }
        RagIndexKbQasRequest req = new RagIndexKbQasRequest();
        req.setKbId(kbId);
        try {
            RagIndexKbQasResponse resp = ragDocRetrieveClient.indexKbQas(req);
            if (resp == null) {
                return null;
            }
            log.info("QA 全部索引已提交: kbId={}, qaCount={}, indexedQa={}, indexGen={}",
                    kbId, resp.getQaCount(), resp.getIndexedQa(), resp.getIndexGeneration());
            return resp.getIndexGeneration();
        } catch (Exception e) {
            log.error("app-rag-doc QA 全部索引失败: kbId={}, error={}", kbId, e.getMessage(), e);
            throw new RuntimeException("QA 索引服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String indexQas(Long kbId, List<Long> qaIds) {
        if (!properties.isEnabled() || kbId == null || qaIds == null || qaIds.isEmpty()) {
            return null;
        }
        RagIndexQasRequest req = new RagIndexQasRequest();
        req.setKbId(kbId);
        req.setQaIds(qaIds);
        req.setOperation("upsert");
        try {
            RagIndexQasResponse resp = ragDocRetrieveClient.indexQas(req);
            if (resp == null || !"success".equalsIgnoreCase(resp.getStatus())) {
                throw new RuntimeException("rag-doc QA增量索引失败: status=" + (resp == null ? "null" : resp.getStatus()));
            }
            log.info("QA增量索引成功: kbId={}, indexed={}", kbId, resp.getIndexedQa());
            return resp.getStatus();
        } catch (Exception e) {
            log.error("app-rag-doc QA增量索引失败: kbId={}, qaIds={}, error={}", kbId, qaIds, e.getMessage(), e);
            throw new RuntimeException("QA 索引服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String deleteQaIndex(Long kbId, List<Long> qaIds) {
        if (!properties.isEnabled() || kbId == null || qaIds == null || qaIds.isEmpty()) {
            return null;
        }
        RagIndexQasRequest req = new RagIndexQasRequest();
        req.setKbId(kbId);
        req.setQaIds(qaIds);
        req.setOperation("delete");
        try {
            RagIndexQasResponse resp = ragDocRetrieveClient.indexQas(req);
            if (resp == null || !"success".equalsIgnoreCase(resp.getStatus())) {
                throw new RuntimeException("rag-doc QA增量删除失败: status=" + (resp == null ? "null" : resp.getStatus()));
            }
            log.info("QA增量删除成功: kbId={}, count={}", kbId, qaIds.size());
            return resp.getStatus();
        } catch (Exception e) {
            log.error("app-rag-doc QA增量删除失败: kbId={}, qaIds={}, error={}", kbId, qaIds, e.getMessage(), e);
            throw new RuntimeException("QA 索引删除服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String deleteFileIndex(Long kbId, Long fileNodeId) {
        if (!properties.isEnabled() || kbId == null || fileNodeId == null) {
            return null;
        }
        RagIndexFileRequest req = new RagIndexFileRequest();
        req.setKbId(kbId);
        req.setFileNodeId(fileNodeId);
        req.setOperation("delete");
        req.setAsyncMode(false);
        try {
            RagIndexFileResponse resp = ragDocRetrieveClient.rebuildFileIndex(req);
            if (resp == null || !"success".equalsIgnoreCase(resp.getStatus())) {
                throw new RuntimeException("rag-doc 文件索引删除失败: status="
                        + (resp == null ? "null" : resp.getStatus()));
            }
            log.info("文件索引删除成功: kbId={}, fileNodeId={}", kbId, fileNodeId);
            return resp.getStatus();
        } catch (Exception e) {
            log.error("app-rag-doc 文件索引删除失败: kbId={}, fileNodeId={}, error={}",
                    kbId, fileNodeId, e.getMessage(), e);
            throw new RuntimeException("文件索引删除服务调用失败: " + e.getMessage(), e);
        }
    }

    @Override
    public String deleteChunkIndex(Long kbId, Long fileNodeId, List<Long> chunkIds) {
        if (!properties.isEnabled() || kbId == null || fileNodeId == null
                || chunkIds == null || chunkIds.isEmpty()) {
            return null;
        }
        RagIndexChunksRequest req = new RagIndexChunksRequest();
        req.setKbId(kbId);
        req.setFileNodeId(fileNodeId);
        req.setChunkIds(chunkIds);
        req.setOperation("delete");
        try {
            RagIndexChunksResponse resp = ragDocRetrieveClient.indexChunks(req);
            if (resp == null || !"success".equalsIgnoreCase(resp.getStatus())) {
                throw new RuntimeException("rag-doc Chunk索引删除失败: status="
                        + (resp == null ? "null" : resp.getStatus()));
            }
            log.info("Chunk索引删除成功: kbId={}, fileNodeId={}, count={}",
                    kbId, fileNodeId, chunkIds.size());
            return resp.getStatus();
        } catch (Exception e) {
            log.error("app-rag-doc Chunk索引删除失败: kbId={}, fileNodeId={}, chunkIds={}, error={}",
                    kbId, fileNodeId, chunkIds, e.getMessage(), e);
            throw new RuntimeException("Chunk 索引删除服务调用失败: " + e.getMessage(), e);
        }
    }

    private RetrievalEngineHit toHit(RagRetrieveResultItem it) {
        RetrievalEngineHit hit = new RetrievalEngineHit();
        hit.setChunkId(it.getChunkId());
        hit.setScore(it.getScore());
        hit.setRetrieverType(firstNonBlank(it.getHitType(), it.getRouteName(), it.getSource()));
        hit.setSnippet(buildSnippet(it));

        Map<String, Object> meta = new HashMap<>(16);
        if (it.getKbId() != null) {
            meta.put("kb_id", it.getKbId());
        }
        if (it.getFileNodeId() != null) {
            meta.put("file_node_id", it.getFileNodeId());
        }
        if (it.getTitle() != null) {
            meta.put("title", it.getTitle());
            meta.put("file_name", it.getTitle());
        }
        putIfNotNull(meta, "field_id", it.getFieldId());
        putIfNotNull(meta, "qa_id", it.getQaId());
        putIfNotBlank(meta, "chunk_type", it.getChunkType());
        putIfNotBlank(meta, "file_center_file_id", it.getFileCenterFileId());
        putIfNotBlank(meta, "visual_asset_id", it.getVisualAssetId());
        putIfNotNull(meta, "field_code", it.getFieldCode());
        putIfNotNull(meta, "field_name_cn", it.getFieldNameCn());
        putIfNotNull(meta, "page_no", it.getPageNo());
        putIfNotNull(meta, "rank", it.getRank());
        putIfNotNull(meta, "route_name", it.getRouteName());
        putIfNotNull(meta, "route_names", it.getRouteNames());
        putIfNotNull(meta, "hit_type", it.getHitType());
        putIfNotNull(meta, "rerank_score", it.getRerankScore());
        putIfNotBlank(meta, "value_text", it.getValueText());
        putIfNotBlank(meta, "evidence_text", firstNonBlank(it.getEvidenceText(), it.getEvidenceQuote()));
        putIfNotNull(meta, "evidence_chain", it.getEvidenceChain());
        putIfNotNull(meta, "graph_path", it.getGraphPath());
        putIfNotBlank(meta, "reason", it.getReason());
        Map<String, Object> firstRaw = firstRawItem(it);
        if (firstRaw != null) {
            putIfNotBlank(meta, "plan_name", stringValue(firstRaw.get("plan_name")));
            putIfNotBlank(meta, "profile", stringValue(firstRaw.get("profile")));
            putIfNotBlank(meta, "source_chunk_id", stringValue(firstRaw.get("source_chunk_id")));
        }
        hit.setMetadata(meta);
        try {
            hit.setRawData(objectMapper.convertValue(it, Map.class));
        } catch (Exception e) {
            log.warn("序列化 rag-doc 原始结果失败 chunkId={}", it.getChunkId(), e);
            hit.setRawData(null);
        }
        return hit;
    }

    private static String buildSnippet(RagRetrieveResultItem it) {
        String c = it.getContent();
        if (c != null && !c.trim().isEmpty()) {
            return c;
        }
        String ev = it.getEvidenceQuote();
        if (ev != null && !ev.trim().isEmpty()) {
            return ev;
        }
        String et = it.getEvidenceText();
        if (et != null && !et.trim().isEmpty()) {
            return et;
        }
        String vt = it.getValueText();
        String fn = it.getFieldNameCn();
        if (fn != null && vt != null) {
            return fn + ": " + vt;
        }
        if (vt != null) {
            return vt;
        }
        return "";
    }

    private static Map<String, Object> firstRawItem(RagRetrieveResultItem it) {
        return it.getRawItems() == null || it.getRawItems().isEmpty() ? null : it.getRawItems().get(0);
    }

    private static String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (value != null && !value.trim().isEmpty()) {
                return value.trim();
            }
        }
        return null;
    }

    private static void putIfNotNull(Map<String, Object> meta, String key, Object value) {
        if (value != null) {
            meta.put(key, value);
        }
    }

    private static void putIfNotBlank(Map<String, Object> meta, String key, String value) {
        if (value != null && !value.trim().isEmpty()) {
            meta.put(key, value.trim());
        }
    }

    private static String stringValue(Object value) {
        return value == null ? null : value.toString();
    }
}
