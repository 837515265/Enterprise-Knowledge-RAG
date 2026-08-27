package com.ludan.app.feign;

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
import feign.RequestInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.Map;

/**
 * 调用 retrieve-service（注册名 app-rag-doc）。
 * <p>
 * 路径与契约以《当前代码接口完整文档》为准。
 *
 * @author ludan
 */
@FeignClient(
        contextId = "appRagDocRetrieveClient",
        name = "${retrieval-engine.service-name:app-rag-doc}",
        configuration = AppRagDocRetrieveClient.FeignClientConfiguration.class
)
public interface AppRagDocRetrieveClient {

    @GetMapping(value = "/api/v1/graph/knowledge-bases/{kbId}")
    Map<String, Object> getKnowledgeBaseGraph(@PathVariable("kbId") Long kbId,
                                               @RequestParam("include_chunks") boolean includeChunks);

    @GetMapping(value = "/api/v1/graph/knowledge-bases/{kbId}/audit")
    Map<String, Object> getKnowledgeBaseGraphAudit(@PathVariable("kbId") Long kbId,
                                                    @RequestParam("hub_degree") int hubDegree,
                                                    @RequestParam("limit") int limit);

    @PostMapping(value = "/api/v1/graph/knowledge-bases/{kbId}/communities/rebuild")
    Map<String, Object> rebuildKnowledgeBaseGraphCommunities(@PathVariable("kbId") Long kbId,
                                                              @RequestParam("min_size") int minSize);

    @GetMapping(value = "/api/v1/graph/files/{fileNodeId}")
    Map<String, Object> getFileGraph(@PathVariable("fileNodeId") Long fileNodeId,
                                     @RequestParam("kb_id") Long kbId,
                                     @RequestParam("include_chunks") boolean includeChunks);

    /**
     * 混合检索主路径：{@code POST /api/v1/retrieve/query}
     */
    @PostMapping(value = "/api/v1/retrieve/query", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagRetrieveQueryResponse retrieveQuery(@RequestBody RagRetrieveQueryRequest body);

    /**
     * 兼容路径：{@code POST /api/v1/retrieve}
     */
    @PostMapping(value = "/api/v1/retrieve", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagRetrieveQueryResponse retrieveCompat(@RequestBody RagRetrieveQueryRequest body);

    /**
     * 文件级索引：{@code POST /api/v1/index/files}
     */
    @PostMapping(value = "/api/v1/index/files", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagIndexFileResponse rebuildFileIndex(@RequestBody RagIndexFileRequest body);

    /**
     * KB 级索引重建：{@code POST /api/v1/index/kb/rebuild}
     */
    @PostMapping(value = "/api/v1/index/kb/rebuild", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagIndexFileResponse rebuildKbIndex(@RequestBody RagIndexKbRebuildRequest body);

    /**
     * QA 全部索引：{@code POST /api/v1/index/kb/qas}
     */
    @PostMapping(value = "/api/v1/index/kb/qas", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagIndexKbQasResponse indexKbQas(@RequestBody RagIndexKbQasRequest body);

    /**
     * QA 增量索引：{@code POST /api/v1/index/qas}
     */
    @PostMapping(value = "/api/v1/index/qas", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagIndexQasResponse indexQas(@RequestBody RagIndexQasRequest body);

    /**
     * Chunk 增量索引：{@code POST /api/v1/index/chunks}
     */
    @PostMapping(value = "/api/v1/index/chunks", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagIndexChunksResponse indexChunks(@RequestBody RagIndexChunksRequest body);

    /**
     * Feign 专属配置（勿加 {@code @Configuration}，避免被全局扫描）
     */
    class FeignClientConfiguration {

        @Bean
        public RequestInterceptor ragDocApiTokenInterceptor(RetrievalEngineProperties retrievalEngineProperties) {
            return template -> {
                String token = retrievalEngineProperties.getApiToken();
                if (StringUtils.hasText(token)) {
                    template.header("X-API-Token", token.trim());
                }
            };
        }
    }
}
