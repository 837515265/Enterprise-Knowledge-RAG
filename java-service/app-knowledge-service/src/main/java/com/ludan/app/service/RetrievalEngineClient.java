package com.ludan.app.service;

import com.ludan.app.service.model.RetrievalEngineHit;
import com.ludan.app.entity.KbFileTask;

import java.util.List;
import java.util.Map;

/**
 * 检索客户端：调用 retrieve-service（app-rag-doc），统一使用 kb_ids 多库接口。
 *
 * @author ludan
 */
public interface RetrievalEngineClient {

    /** 读取 Neo4j 中的知识库级知识图谱。 */
    Map<String, Object> getKnowledgeBaseGraph(Long kbId, boolean includeChunks);

    /** 读取图谱质量、hub、孤儿事实和 surprise 排名。 */
    Map<String, Object> getKnowledgeBaseGraphAudit(Long kbId, int hubDegree, int limit);

    /** 重建知识库社区及全局社区报告。 */
    Map<String, Object> rebuildKnowledgeBaseGraphCommunities(Long kbId, int minSize);

    /** 读取 Neo4j 中的文档级知识子图。 */
    Map<String, Object> getFileGraph(Long kbId, Long fileNodeId, boolean includeChunks);

    /**
     * 对多个知识库执行混合检索（单次 HTTP，引擎侧 kb_ids）。
     * 单库场景请使用 {@code Collections.singletonList(kbId)} 包装。
     *
     * @param kbIds   知识库 ID 列表
     * @param query   查询文本
     * @param topK    top_k
     * @param options 文档 options
     */
    List<RetrievalEngineHit> retrieveForKnowledgeBases(List<Long> kbIds, String query, int topK,
                                                        Map<String, Object> options);

    /**
     * 文件解析成功后重建该文件索引。
     */
    String rebuildFileIndex(KbFileTask task);

    /**
     * KB 级索引重建（不重新解析，直接用已有 chunks 重建索引）。
     */
    String rebuildKbIndex(Long kbId);

    /**
     * QA 全部索引（使用知识库下已审核通过的 QA 对重建索引）。
     */
    String rebuildQaIndex(Long kbId);

    /**
     * QA 增量索引（upsert）。仅用于创建/更新场景；删除场景仍走 {@link #rebuildQaIndex}。
     *
     * @param kbId  知识库ID
     * @param qaIds 待索引的 QA ID 列表
     * @return 索引状态字符串
     */
    String indexQas(Long kbId, List<Long> qaIds);

    /**
     * QA 增量索引删除（从向量库移除指定 QA）。
     *
     * @param kbId  知识库ID
     * @param qaIds 待删除的 QA ID 列表
     * @return 索引状态字符串
     */
    String deleteQaIndex(Long kbId, List<Long> qaIds);

    /**
     * 文件级索引删除（从向量库移除该文件全部文档索引）。
     *
     * @param kbId       知识库ID
     * @param fileNodeId 文件节点ID
     * @return 索引状态字符串
     */
    String deleteFileIndex(Long kbId, Long fileNodeId);

    /**
     * Chunk 增量索引删除（从向量库移除指定 Chunk）。
     *
     * @param kbId       知识库ID
     * @param fileNodeId 文件节点ID
     * @param chunkIds   待删除的 Chunk ID 列表
     * @return 索引状态字符串
     */
    String deleteChunkIndex(Long kbId, Long fileNodeId, List<Long> chunkIds);

    /**
     * 检索并返回 LLM 上下文（llm_context），不返回检索 results。
     */
    String retrieveLlmContext(List<Long> kbIds, String query, Integer topK, Map<String, Object> options);
}
