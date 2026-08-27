package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.dto.resp.ChunkStatsRespDTO;
import com.ludan.app.entity.KbChunk;
import com.ludan.app.entity.KbChunkRevision;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbChunkMapper;
import com.ludan.app.mapper.KbChunkRevisionMapper;
import com.ludan.app.mapper.KbFileTaskMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.service.KbChunkService;
import com.ludan.app.service.KbFileNodeService;
import com.ludan.app.service.RetrievalEngineClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.collections4.MapUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.Map;

/**
 * Chunk 管理 Service 实现
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbChunkServiceImpl
        extends SuperServiceImpl<KbChunkMapper, KbChunk>
        implements KbChunkService {

    private final KbChunkRevisionMapper chunkRevisionMapper;
    private final KbKnowledgeBaseMapper knowledgeBaseMapper;
    private final KbFileNodeService fileNodeService;
    private final KbFileTaskMapper fileTaskMapper;
    private final RetrievalEngineClient retrievalEngineClient;

    @Override
    public Page<KbChunk> findByFileNode(Map<String, Object> params) {
        Page<KbChunk> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 10)
        );
        return baseMapper.findByFileNode(page, params);
    }

    @Override
    public ChunkStatsRespDTO getChunkStats(Long fileNodeId) {
        ChunkStatsRespDTO stats = new ChunkStatsRespDTO();
        // 查询时包含已删除的记录以统计 deletedChunkCount
        long total = this.count(new LambdaQueryWrapper<KbChunk>()
                .eq(KbChunk::getFileNodeId, fileNodeId));
        long available = this.count(new LambdaQueryWrapper<KbChunk>()
                .eq(KbChunk::getFileNodeId, fileNodeId)
                .eq(KbChunk::getEnabled, 1)
                .eq(KbChunk::getAuditStatus, "approved"));
        stats.setTotalChunkCount((int) total);
        stats.setAvailableChunkCount((int) available);
        stats.setDeletedChunkCount(0);
        return stats;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void editChunk(Long chunkId, String newContent, String editReason) {
        KbChunk chunk = this.getById(chunkId);
        if (chunk == null) {
            throw new RuntimeException("Chunk不存在");
        }

        KbChunkRevision previousRevision = null;
        if (chunk.getLatestRevisionId() != null) {
            previousRevision = chunkRevisionMapper.selectById(chunk.getLatestRevisionId());
        }

        // 计算新版本号
        Integer maxRevNo = chunkRevisionMapper.getMaxRevisionNo(chunkId);
        int newRevNo = (maxRevNo != null ? maxRevNo : 0) + 1;

        // 创建新 revision
        KbChunkRevision rev = new KbChunkRevision();
        rev.setKbId(chunk.getKbId());
        rev.setFileNodeId(chunk.getFileNodeId());
        rev.setChunkId(chunkId);
        rev.setRevisionNo(newRevNo);
        rev.setRevisionSource("manual_edit");
        rev.setBaseRevisionId(chunk.getLatestRevisionId());
        rev.setContent(newContent);
        inheritRevisionFields(rev, previousRevision, chunk, newContent);
        rev.setEditReason(editReason);
        chunkRevisionMapper.insert(rev);

        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(chunk.getKbId());
        boolean auditEnabled = kb != null && Integer.valueOf(1).equals(kb.getFileAuditEnabled());

        // 更新 chunk 指针：开启审核则回到 pending；关闭审核则直接发布新版本并等待重建索引。
        chunk.setLatestRevisionId(rev.getId());
        if (auditEnabled) {
            chunk.setAuditStatus("pending");
            chunk.setEnabled(0);
        } else {
            chunk.setAuditStatus("approved");
            chunk.setEnabled(1);
            chunk.setPublishedRevisionId(rev.getId());
            chunk.setContent(rev.getContent());
            chunk.setSummary(rev.getSummary());
            chunk.setContentHash(sha256Hex(rev.getContent()));
            chunk.setIndexSyncStatus("none");
            chunk.setIndexGeneration(null);
        }
        this.updateById(chunk);
        if (!auditEnabled) {
            triggerFileIndexRebuildAfterCommit(chunk);
        }
    }

    private void inheritRevisionFields(KbChunkRevision target,
                                       KbChunkRevision previousRevision,
                                       KbChunk chunk,
                                       String newContent) {
        target.setSummary(firstNonNull(
                previousRevision != null ? previousRevision.getSummary() : null,
                chunk.getSummary()));
        target.setContentForEmbedding(firstText(
                previousRevision != null ? previousRevision.getContentForEmbedding() : null,
                newContent));
        target.setContentForBm25(firstText(
                previousRevision != null ? previousRevision.getContentForBm25() : null,
                newContent));
        target.setTitle(firstNonNull(
                previousRevision != null ? previousRevision.getTitle() : null,
                chunk.getTitle()));
        target.setTitlePath(firstNonNull(
                previousRevision != null ? previousRevision.getTitlePath() : null,
                chunk.getTitlePath()));
        target.setPageStart(firstNonNull(
                previousRevision != null ? previousRevision.getPageStart() : null,
                chunk.getPageStart()));
        target.setPageEnd(firstNonNull(
                previousRevision != null ? previousRevision.getPageEnd() : null,
                chunk.getPageEnd()));
        target.setBlockIds(firstNonNull(
                previousRevision != null ? previousRevision.getBlockIds() : null,
                chunk.getBlockIds()));
        target.setBboxJson(previousRevision != null ? previousRevision.getBboxJson() : null);
        target.setMetadataJson(firstNonNull(
                previousRevision != null ? previousRevision.getMetadataJson() : null,
                chunk.getMetadataJson()));
    }

    private <T> T firstNonNull(T preferred, T fallback) {
        return preferred != null ? preferred : fallback;
    }

    private String firstText(String preferred, String fallback) {
        return preferred != null && !preferred.trim().isEmpty() ? preferred : fallback;
    }

    private String sha256Hex(String content) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest((content == null ? "" : content).getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(hashed.length * 2);
            for (byte b : hashed) {
                out.append(String.format("%02x", b));
            }
            return out.toString();
        } catch (Exception e) {
            throw new RuntimeException("内容Hash计算失败", e);
        }
    }

    @Override
    public void toggleEnabled(Long chunkId, boolean enabled) {
        KbChunk chunk = this.getById(chunkId);
        if (chunk == null) {
            throw new RuntimeException("Chunk不存在");
        }
        chunk.setEnabled(enabled ? 1 : 0);
        this.updateById(chunk);
    }

    /**
     * 硬删 Chunk：先删 revision，再删主表，最后尽力同步向量索引删除。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteChunk(Long kbId, Long chunkId) {
        KbChunk chunk = this.getById(chunkId);
        if (chunk == null || !kbId.equals(chunk.getKbId())) {
            throw new RuntimeException("Chunk不存在");
        }
        Long fileNodeId = chunk.getFileNodeId();
        chunkRevisionMapper.physicalDeleteByChunkId(chunkId);
        baseMapper.physicalDeleteById(chunkId);
        try {
            retrievalEngineClient.deleteChunkIndex(kbId, fileNodeId, Collections.singletonList(chunkId));
        } catch (Exception e) {
            log.warn("删除Chunk后索引同步失败: kbId={}, fileNodeId={}, chunkId={}, msg={}",
                    kbId, fileNodeId, chunkId, e.getMessage());
        }
    }

    private void triggerFileIndexRebuildAfterCommit(KbChunk chunk) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    rebuildFileIndex(chunk);
                }
            });
        } else {
            rebuildFileIndex(chunk);
        }
    }

    private void rebuildFileIndex(KbChunk chunk) {
        KbFileNode node = fileNodeService.getById(chunk.getFileNodeId());
        KbFileTask task = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getKbId, chunk.getKbId())
                .eq(KbFileTask::getFileNodeId, chunk.getFileNodeId())
                .orderByDesc(KbFileTask::getCreateTime)
                .last("LIMIT 1"));
        if (task == null) {
            task = new KbFileTask();
            task.setKbId(chunk.getKbId());
            task.setFileNodeId(chunk.getFileNodeId());
            task.setParseGeneration(chunk.getParseGeneration());
        }
        try {
            String indexTaskId = retrievalEngineClient.rebuildFileIndex(task);
            task.setStage("index");
            task.setIndexSyncStatus("syncing");
            task.setIndexGeneration(chunk.getParseGeneration());
            task.setErrorMsg(null);
            if (indexTaskId != null && !indexTaskId.trim().isEmpty()) {
                task.setEngineTaskId(indexTaskId.trim());
            }
            if (task.getId() != null) {
                fileTaskMapper.updateById(task);
            }
            if (node != null) {
                node.setIndexStatus("indexing");
                fileNodeService.updateById(node);
            }
        } catch (Exception e) {
            log.error("编辑Chunk后触发文件索引重建失败: kbId={}, fileNodeId={}, chunkId={}",
                    chunk.getKbId(), chunk.getFileNodeId(), chunk.getId(), e);
            if (task.getId() != null) {
                task.setStage("index");
                task.setIndexSyncStatus("failed");
                task.setErrorMsg("索引服务调用失败: " + e.getMessage());
                fileTaskMapper.updateById(task);
            }
            if (node != null) {
                node.setIndexStatus("failed");
                fileNodeService.updateById(node);
            }
        }
    }
}
