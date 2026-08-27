package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.ISuperService;
import com.ludan.app.dto.resp.ChunkStatsRespDTO;
import com.ludan.app.entity.KbChunk;

import java.util.Map;

/**
 * Chunk 管理 Service
 *
 * @author ludan
 */
public interface KbChunkService extends ISuperService<KbChunk> {

    /**
     * 查询指定文件下的 Chunk 列表
     */
    Page<KbChunk> findByFileNode(Map<String, Object> params);

    /**
     * Chunk 统计
     */
    ChunkStatsRespDTO getChunkStats(Long fileNodeId);

    /**
     * 编辑 Chunk（创建新 revision）
     */
    void editChunk(Long chunkId, String newContent, String editReason);

    /**
     * 启用/禁用 Chunk
     */
    void toggleEnabled(Long chunkId, boolean enabled);

    /**
     * 硬删指定 Chunk 及其 revision，并尽力清理向量索引。
     *
     * @param kbId    知识库 ID
     * @param chunkId Chunk ID
     */
    void deleteChunk(Long kbId, Long chunkId);
}
