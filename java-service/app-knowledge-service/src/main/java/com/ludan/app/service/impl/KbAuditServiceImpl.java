package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.entity.KbAuditHistory;
import com.ludan.app.entity.KbChunk;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.entity.KbQaPair;
import com.ludan.app.entity.KbChunkRevision;
import com.ludan.app.mapper.KbAuditHistoryMapper;
import com.ludan.app.mapper.KbFileTaskMapper;
import com.ludan.app.mapper.KbChunkRevisionMapper;
import com.ludan.app.service.KbAuditService;
import com.ludan.app.service.KbChunkService;
import com.ludan.app.service.KbFileNodeService;
import com.ludan.app.service.KbOperationLogService;
import com.ludan.app.service.KbQaPairService;
import com.ludan.app.service.RetrievalEngineClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.collections4.MapUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import javax.servlet.http.HttpServletRequest;
import java.net.URLDecoder;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Date;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 审核 Service 实现
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbAuditServiceImpl implements KbAuditService {

    private static final String USER_ID_HEADER = "x-userid-header";
    private static final String REAL_NAME_HEADER = "x-realname-header";
    private static final String SYSTEM_REVIEWER = "system";
    private static final int REVIEW_COMMENT_MAX_LENGTH = 1000;
    private static final int REJECT_REASON_MAX_LENGTH = 500;

    private final KbAuditHistoryMapper auditHistoryMapper;
    private final KbChunkService chunkService;
    private final KbChunkRevisionMapper chunkRevisionMapper;
    private final KbQaPairService qaPairService;
    private final KbFileNodeService fileNodeService;
    private final KbFileTaskMapper fileTaskMapper;
    private final KbOperationLogService operationLogService;
    private final RetrievalEngineClient retrievalEngineClient;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void submitFileAudit(Long kbId, Long fileNodeId, String status, String reviewComment,
                                List<Long> approvedIds, List<Long> rejectedIds, String rejectReason,
                                Map<String, Object> rejectedReasons) {
        Map<Long, KbChunk> chunks = loadAndValidateFileChunks(kbId, fileNodeId, approvedIds, rejectedIds);

        // 更新被通过的 chunk 状态
        if (approvedIds != null) {
            for (Long chunkId : approvedIds) {
                KbChunk chunk = chunks.get(chunkId);
                publishLatestRevision(chunk);
                chunkService.updateById(chunk);
            }
        }

        // 更新被驳回的 chunk 状态
        if (rejectedIds != null) {
            for (Long chunkId : rejectedIds) {
                KbChunk chunk = chunks.get(chunkId);
                rejectLatestRevision(chunk, truncate(resolveRejectReason(chunkId, rejectedReasons, rejectReason),
                        REJECT_REASON_MAX_LENGTH));
                chunkService.updateById(chunk);
            }
        }

        // 记录审核历史
        KbAuditHistory history = new KbAuditHistory();
        history.setKbId(kbId);
        history.setBizType("chunk");
        history.setBizId(fileNodeId);
        history.setStatus(status);
        history.setReviewComment(truncate(reviewComment, REVIEW_COMMENT_MAX_LENGTH));
        history.setReviewedAt(new Date());
        fillReviewer(history);
        try {
            if (approvedIds != null) {
                history.setApprovedIds(objectMapper.writeValueAsString(approvedIds));
            }
            if (rejectedIds != null) {
                history.setRejectedIds(objectMapper.writeValueAsString(rejectedIds));
            }
        } catch (Exception e) {
            log.error("JSON序列化失败", e);
        }
        auditHistoryMapper.insert(history);

        recordChunkAuditOperationLog(kbId, fileNodeId, status, approvedIds, rejectedIds, reviewComment);
        triggerChunkIndexSync(kbId, fileNodeId, approvedIds);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void submitQaAudit(Long kbId, Long qaId, String status, String reviewComment) {
        KbQaPair qa = qaPairService.getById(qaId);
        if (qa == null) {
            throw new RuntimeException("问答对不存在");
        }
        qa.setAuditStatus(status);
        if ("approved".equals(status)) {
            qa.setIndexSyncStatus("none");
            triggerQaIndexSync(kbId, Collections.singletonList(qaId));
        }
        qaPairService.updateById(qa);

        KbAuditHistory history = new KbAuditHistory();
        history.setKbId(kbId);
        history.setBizType("qa");
        history.setBizId(qaId);
        history.setStatus(status);
        history.setReviewComment(truncate(reviewComment, REVIEW_COMMENT_MAX_LENGTH));
        history.setReviewedAt(new Date());
        fillReviewer(history);
        auditHistoryMapper.insert(history);

        recordQaAuditOperationLog(kbId, qaId, status, reviewComment);
    }

    @Override
    public Page<KbAuditHistory> getHistory(Map<String, Object> params) {
        Page<KbAuditHistory> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 10)
        );
        return auditHistoryMapper.findList(page, params);
    }

    private void triggerQaIndexSync(Long kbId, List<Long> qaIds) {
        if (qaIds == null || qaIds.isEmpty()) {
            return;
        }
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    try {
                        retrievalEngineClient.indexQas(kbId, qaIds);
                    } catch (Exception e) {
                        log.warn("QA审核通过后索引同步失败(afterCommit) kbId={} qaIds={} msg={}", kbId, qaIds, e.getMessage());
                    }
                }
            });
        } else {
            try {
                retrievalEngineClient.indexQas(kbId, qaIds);
            } catch (Exception e) {
                log.warn("QA审核通过后索引同步失败 kbId={} qaIds={} msg={}", kbId, qaIds, e.getMessage());
            }
        }
    }

    private void fillReviewer(KbAuditHistory history) {
        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes == null) {
            history.setReviewer(SYSTEM_REVIEWER);
            history.setReviewerName(SYSTEM_REVIEWER);
            return;
        }

        HttpServletRequest request = attributes.getRequest();
        String reviewer = normalizeBlank(request.getHeader(USER_ID_HEADER));
        String reviewerName = decodeHeader(normalizeBlank(request.getHeader(REAL_NAME_HEADER)));
        history.setReviewer(reviewer != null ? reviewer : SYSTEM_REVIEWER);
        history.setReviewerName(reviewerName != null ? reviewerName : history.getReviewer());
    }

    private String normalizeBlank(String value) {
        return value == null || value.trim().isEmpty() ? null : value.trim();
    }

    private String decodeHeader(String value) {
        if (value == null) {
            return null;
        }
        try {
            return URLDecoder.decode(value, StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            return value;
        }
    }

    private String resolveRejectReason(Long chunkId, Map<String, Object> rejectedReasons, String fallback) {
        if (rejectedReasons == null || chunkId == null) {
            return fallback;
        }
        Object reason = rejectedReasons.get(String.valueOf(chunkId));
        if (reason == null) {
            reason = rejectedReasons.get(chunkId);
        }
        return reason == null ? fallback : String.valueOf(reason);
    }

    private Map<Long, KbChunk> loadAndValidateFileChunks(Long kbId, Long fileNodeId,
                                                        List<Long> approvedIds, List<Long> rejectedIds) {
        KbFileNode fileNode = fileNodeService.getById(fileNodeId);
        if (fileNode == null || !kbId.equals(fileNode.getKbId())) {
            throw new RuntimeException("文件不存在或不属于当前知识库");
        }

        LinkedHashSet<Long> allIds = new LinkedHashSet<>();
        addIds(allIds, approvedIds);
        addIds(allIds, rejectedIds);
        if (allIds.isEmpty()) {
            return new LinkedHashMap<>();
        }
        if (hasIntersection(approvedIds, rejectedIds)) {
            throw new RuntimeException("同一Chunk不能同时通过和驳回");
        }

        List<KbChunk> chunkList = chunkService.list(new LambdaQueryWrapper<KbChunk>()
                .in(KbChunk::getId, allIds));
        Map<Long, KbChunk> chunks = new LinkedHashMap<>();
        if (chunkList != null) {
            for (KbChunk chunk : chunkList) {
                chunks.put(chunk.getId(), chunk);
            }
        }

        for (Long chunkId : allIds) {
            KbChunk chunk = chunks.get(chunkId);
            if (chunk == null) {
                throw new RuntimeException("Chunk不存在: " + chunkId);
            }
            if (!kbId.equals(chunk.getKbId()) || !fileNodeId.equals(chunk.getFileNodeId())) {
                throw new RuntimeException("Chunk不属于当前知识库或文件: " + chunkId);
            }
            if (!"pending".equals(chunk.getAuditStatus())) {
                throw new RuntimeException("Chunk不是待审核状态: " + chunkId);
            }
        }
        return chunks;
    }

    private void addIds(Set<Long> target, Collection<Long> ids) {
        if (ids == null) {
            return;
        }
        for (Long id : ids) {
            if (id == null) {
                throw new RuntimeException("Chunk ID不能为空");
            }
            target.add(id);
        }
    }

    private boolean hasIntersection(Collection<Long> left, Collection<Long> right) {
        if (left == null || right == null || left.isEmpty() || right.isEmpty()) {
            return false;
        }
        Set<Long> seen = new HashSet<>(left);
        for (Long id : right) {
            if (seen.contains(id)) {
                return true;
            }
        }
        return false;
    }

    private void publishLatestRevision(KbChunk chunk) {
        KbChunkRevision revision = requireRevision(chunk.getLatestRevisionId(), chunk.getId());
        chunk.setPublishedRevisionId(revision.getId());
        chunk.setContent(revision.getContent());
        chunk.setSummary(revision.getSummary());
        chunk.setContentHash(sha256Hex(revision.getContent()));
        chunk.setAuditStatus("approved");
        chunk.setRejectReason(null);
        chunk.setEnabled(1);
        chunk.setIndexSyncStatus("none");
        chunk.setIndexGeneration(null);
    }

    private void rejectLatestRevision(KbChunk chunk, String rejectReason) {
        chunk.setAuditStatus("rejected");
        chunk.setRejectReason(rejectReason);
        if (chunk.getPublishedRevisionId() == null) {
            chunk.setEnabled(0);
            return;
        }

        KbChunkRevision publishedRevision = requireRevision(chunk.getPublishedRevisionId(), chunk.getId());
        chunk.setContent(publishedRevision.getContent());
        chunk.setSummary(publishedRevision.getSummary());
        chunk.setContentHash(sha256Hex(publishedRevision.getContent()));
        chunk.setEnabled(1);
    }

    private KbChunkRevision requireRevision(Long revisionId, Long chunkId) {
        if (revisionId == null) {
            throw new RuntimeException("Chunk缺少版本: " + chunkId);
        }
        KbChunkRevision revision = chunkRevisionMapper.selectById(revisionId);
        if (revision == null || !chunkId.equals(revision.getChunkId())) {
            throw new RuntimeException("Chunk版本不存在或不匹配: " + chunkId);
        }
        return revision;
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

    private void recordChunkAuditOperationLog(Long kbId, Long fileNodeId, String status,
                                             List<Long> approvedIds, List<Long> rejectedIds,
                                             String reviewComment) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("approved_ids", approvedIds);
        detail.put("rejected_ids", rejectedIds);
        detail.put("review_comment", reviewComment);

        operationLogService.log(
                kbId,
                currentOperatorId(),
                resolveAuditAction(status),
                "chunk",
                String.valueOf(fileNodeId),
                "提交Chunk审核",
                toJson(detail)
        );
    }

    private void recordQaAuditOperationLog(Long kbId, Long qaId, String status, String reviewComment) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("qa_id", qaId);
        detail.put("status", status);
        detail.put("review_comment", reviewComment);

        operationLogService.log(
                kbId,
                currentOperatorId(),
                resolveAuditAction(status),
                "qa",
                String.valueOf(qaId),
                "提交QA审核",
                toJson(detail)
        );
    }

    private void triggerChunkIndexSync(Long kbId, Long fileNodeId, List<Long> approvedIds) {
        if (approvedIds == null || approvedIds.isEmpty()) {
            return;
        }

        List<Long> chunkIds = new ArrayList<>(approvedIds);
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    rebuildApprovedChunkIndex(kbId, fileNodeId, chunkIds);
                }
            });
        } else {
            rebuildApprovedChunkIndex(kbId, fileNodeId, chunkIds);
        }
    }

    private void rebuildApprovedChunkIndex(Long kbId, Long fileNodeId, List<Long> approvedIds) {

        KbFileNode node = fileNodeService.getById(fileNodeId);
        KbFileTask task = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getKbId, kbId)
                .eq(KbFileTask::getFileNodeId, fileNodeId)
                .orderByDesc(KbFileTask::getCreateTime)
                .last("LIMIT 1"));
        if (task == null) {
            task = new KbFileTask();
            task.setKbId(kbId);
            task.setFileNodeId(fileNodeId);
        }
        try {
            String indexTaskId = retrievalEngineClient.rebuildFileIndex(task);
            task.setStage("index");
            task.setIndexSyncStatus("syncing");
            task.setIndexGeneration(task.getParseGeneration());
            task.setIndexedChunkCount(approvedIds.size());
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
            log.error("触发文件索引重建失败: taskId={}, kbId={}, fileNodeId={}",
                    task.getId(), kbId, fileNodeId, e);
            if (task.getId() != null) {
                task.setIndexSyncStatus("failed");
                task.setErrorMsg(truncate("索引服务调用失败: " + e.getMessage(), 2000));
                fileTaskMapper.updateById(task);
            }
            if (node != null) {
                node.setIndexStatus("failed");
                fileNodeService.updateById(node);
            }
        }
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private String resolveAuditAction(String status) {
        if ("rejected".equals(status)) {
            return "audit.reject";
        }
        if ("partially_approved".equals(status)) {
            return "audit.partial_approve";
        }
        return "audit.approve";
    }

    private Long currentOperatorId() {
        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes == null) {
            return 0L;
        }
        String reviewer = normalizeBlank(attributes.getRequest().getHeader(USER_ID_HEADER));
        if (reviewer == null) {
            return 0L;
        }
        try {
            return Long.valueOf(reviewer);
        } catch (NumberFormatException e) {
            return 0L;
        }
    }

    private String toJson(Map<String, Object> detail) {
        try {
            return objectMapper.writeValueAsString(detail);
        } catch (Exception e) {
            return "{}";
        }
    }
}
