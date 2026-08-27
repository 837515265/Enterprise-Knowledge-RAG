package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ludan.app.config.ParseEngineProperties;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbFileTaskMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.service.KbFileNodeService;
import com.ludan.app.service.ParseEngineClient;
import com.ludan.app.service.RetrievalEngineClient;
import com.ludan.app.service.model.ParseTaskStatusSnapshot;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * 解析任务状态同步
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbParseTaskStatusSyncService {

    private static final List<String> ACTIVE_TASK_STATUSES = Arrays.asList("pending", "processing");

    private final KbFileTaskMapper fileTaskMapper;
    private final KbFileNodeService fileNodeService;
    private final ParseEngineClient parseEngineClient;
    private final RetrievalEngineClient retrievalEngineClient;
    private final ParseEngineProperties parseEngineProperties;
    private final KbKnowledgeBaseMapper knowledgeBaseMapper;

    @Scheduled(
            initialDelayString = "${parse-engine.poll-initial-delay-ms:10000}",
            fixedDelayString = "${parse-engine.poll-fixed-delay-ms:10000}"
    )
    public void syncParseTaskStatus() {
        if (!parseEngineProperties.isEnabled() || !parseEngineProperties.isPollEnabled()) {
            return;
        }

        List<KbFileTask> tasks = fileTaskMapper.selectList(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getStage, "parse")
                .in(KbFileTask::getStatus, ACTIVE_TASK_STATUSES)
                .orderByAsc(KbFileTask::getId)
                .last("limit " + Math.max(parseEngineProperties.getPollBatchSize(), 1)));
        if (tasks == null || tasks.isEmpty()) {
            return;
        }

        for (KbFileTask task : tasks) {
            try {
                ParseTaskStatusSnapshot snapshot = parseEngineClient.queryParseTaskStatus(task);
                if (snapshot == null || isBlank(snapshot.getStatus())) {
                    continue;
                }
                applyPolledStatus(task.getId(), snapshot);
            } catch (Exception e) {
                log.warn("轮询解析任务状态异常: taskId={}, error={}", task.getId(), e.getMessage(), e);
            }
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void applyPolledStatus(Long taskId, ParseTaskStatusSnapshot snapshot) {
        if (taskId == null || snapshot == null || isBlank(snapshot.getStatus())) {
            return;
        }

        KbFileTask task = fileTaskMapper.selectById(taskId);
        if (task == null) {
            return;
        }

        String normalizedStatus = snapshot.getStatus().trim().toLowerCase(Locale.ROOT);
        task.setStage(isBlank(snapshot.getStage()) ? task.getStage() : snapshot.getStage().trim());
        if (!isBlank(snapshot.getEngineTaskId()) && isBlank(task.getEngineTaskId())) {
            task.setEngineTaskId(snapshot.getEngineTaskId().trim());
        }

        if ("queued".equals(normalizedStatus) || "pending".equals(normalizedStatus)) {
            task.setStatus("pending");
            task.setErrorMsg(null);
            fileTaskMapper.updateById(task);
            return;
        }

        if ("running".equals(normalizedStatus) || "processing".equals(normalizedStatus)) {
            task.setStatus("processing");
            task.setErrorMsg(null);
            fileTaskMapper.updateById(task);
            keepNodeParsing(task.getFileNodeId(), task.getId());
            return;
        }

        if ("success".equals(normalizedStatus) || "succeeded".equals(normalizedStatus)) {
            task.setStatus("success");
            task.setErrorMsg(null);
            task.setIndexedChunkCount(snapshot.getChunkCount() == null ? 0 : snapshot.getChunkCount());
            fileTaskMapper.updateById(task);
            markNodeParsedIfLatest(task);
            triggerFileIndexRebuild(task);
            return;
        }

        if ("failed".equals(normalizedStatus)) {
            task.setStatus("failed");
            task.setErrorMsg(truncate(snapshot.getErrorMsg(), 2000));
            fileTaskMapper.updateById(task);
            markNodeFailedIfLatest(task);
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void applyCallback(Long taskId, Long fileNodeId, String stage, String status, String parseGeneration,
                              String indexGeneration, String engineTaskId, String parseResultUrl,
                              Integer chunkCount, String errorMsg) {
        KbFileTask task = fileTaskMapper.selectById(taskId);
        if (task == null) {
            return;
        }

        if (!isBlank(stage)) {
            task.setStage(stage.trim());
        }
        if (!isBlank(indexGeneration)) {
            task.setIndexGeneration(indexGeneration.trim());
        }
        if (!isBlank(engineTaskId)) {
            task.setEngineTaskId(engineTaskId.trim());
        }
        if (!isBlank(parseResultUrl)) {
            task.setParseResultUrl(parseResultUrl.trim());
        }

        if ("success".equalsIgnoreCase(status)) {
            task.setStatus("success");
            task.setErrorMsg(null);
            task.setIndexedChunkCount(chunkCount == null ? 0 : chunkCount);
            fileTaskMapper.updateById(task);
            markNodeParsedIfLatest(task, fileNodeId, parseGeneration);
            triggerFileIndexRebuild(task);
            return;
        }

        task.setStatus("failed");
        task.setErrorMsg(truncate(errorMsg, 2000));
        fileTaskMapper.updateById(task);
        markNodeFailedIfLatest(task, fileNodeId);
    }

    @Transactional(rollbackFor = Exception.class)
    public boolean applyIndexCallback(Long kbId, Long fileNodeId, String status, String indexGeneration,
                                      Integer indexedChunks, String errorMsg) {
        if (kbId == null || fileNodeId == null || isBlank(status)) {
            return false;
        }

        KbFileTask task = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getKbId, kbId)
                .eq(KbFileTask::getFileNodeId, fileNodeId)
                .in(KbFileTask::getStage, Arrays.asList("parse", "index"))
                .orderByDesc(KbFileTask::getId)
                .last("limit 1"));
        if (task == null) {
            return false;
        }

        String normalizedStatus = status.trim().toLowerCase(Locale.ROOT);
        if (!isBlank(indexGeneration)) {
            task.setIndexGeneration(indexGeneration.trim());
        }
        if (indexedChunks != null) {
            task.setIndexedChunkCount(indexedChunks);
        }

        if ("accepted".equals(normalizedStatus) || "queued".equals(normalizedStatus)
                || "running".equals(normalizedStatus) || "processing".equals(normalizedStatus)
                || "syncing".equals(normalizedStatus)) {
            task.setIndexSyncStatus("syncing");
            task.setErrorMsg(null);
            fileTaskMapper.updateById(task);
            markNodeIndexStatus(fileNodeId, "indexing", null);
            return true;
        }

        if ("success".equals(normalizedStatus) || "succeeded".equals(normalizedStatus)
                || "synced".equals(normalizedStatus) || "done".equals(normalizedStatus)) {
            task.setIndexSyncStatus("synced");
            task.setErrorMsg(null);
            fileTaskMapper.updateById(task);
            markNodeIndexStatus(fileNodeId, "synced", task.getIndexGeneration());
            return true;
        }

        if ("failed".equals(normalizedStatus) || "fail".equals(normalizedStatus)
                || "error".equals(normalizedStatus)) {
            task.setIndexSyncStatus("failed");
            task.setErrorMsg(truncate(errorMsg, 2000));
            fileTaskMapper.updateById(task);
            markNodeIndexStatus(fileNodeId, "failed", null);
            return true;
        }

        log.warn("未知索引回调状态: kbId={}, fileNodeId={}, status={}", kbId, fileNodeId, status);
        return false;
    }

    private void keepNodeParsing(Long fileNodeId, Long taskId) {
        if (fileNodeId == null || !isLatestTask(fileNodeId, taskId)) {
            return;
        }
        KbFileNode node = fileNodeService.getById(fileNodeId);
        if (node == null || "folder".equals(node.getNodeType())) {
            return;
        }
        if (!"parsing".equals(node.getParseStatus())) {
            node.setParseStatus("parsing");
            fileNodeService.updateById(node);
        }
    }

    private void markNodeParsedIfLatest(KbFileTask task) {
        markNodeParsedIfLatest(task, task.getFileNodeId(), task.getParseGeneration());
    }

    private void markNodeParsedIfLatest(KbFileTask task, Long fileNodeId, String parseGeneration) {
        if (fileNodeId == null || !isLatestTask(fileNodeId, task.getId())) {
            return;
        }
        KbFileNode node = fileNodeService.getById(fileNodeId);
        if (node == null || "folder".equals(node.getNodeType())) {
            return;
        }
        node.setParseStatus("parsed");
        node.setCurrentParseGeneration(isBlank(parseGeneration) ? task.getParseGeneration() : parseGeneration.trim());
        fileNodeService.updateById(node);
    }

    private void triggerFileIndexRebuild(KbFileTask task) {
        if (task == null || task.getId() == null) {
            return;
        }
        // 检查知识库是否开启文件审核，开启则跳过自动索引（等审核通过后由审核流程触发）
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(task.getKbId());
        if (kb != null && kb.getFileAuditEnabled() != null && kb.getFileAuditEnabled() == 1) {
            log.info("知识库已开启文件审核，跳过自动索引: kbId={}, taskId={}", task.getKbId(), task.getId());
            return;
        }
        KbFileTask current = fileTaskMapper.selectById(task.getId());
        if (current == null || "syncing".equals(current.getIndexSyncStatus()) || "synced".equals(current.getIndexSyncStatus())) {
            return;
        }
        try {
            current.setIndexSyncStatus("syncing");
            current.setErrorMsg(null);
            fileTaskMapper.updateById(current);

            KbFileNode node = fileNodeService.getById(current.getFileNodeId());
            if (node != null && !"folder".equals(node.getNodeType())) {
                node.setIndexStatus("indexing");
                fileNodeService.updateById(node);
            }

            retrievalEngineClient.rebuildFileIndex(current);
        } catch (Exception e) {
            log.error("触发文件索引重建失败: taskId={}, fileNodeId={}", current.getId(), current.getFileNodeId(), e);
            current.setIndexSyncStatus("failed");
            current.setErrorMsg(truncate("索引服务调用失败: " + e.getMessage(), 2000));
            fileTaskMapper.updateById(current);
            KbFileNode node = fileNodeService.getById(current.getFileNodeId());
            if (node != null && !"folder".equals(node.getNodeType())) {
                node.setIndexStatus("failed");
                fileNodeService.updateById(node);
            }
        }
    }

    /**
     * 单文件级重新索引：跳过解析，直接从已有 chunks 重建索引。
     */
    @Transactional(rollbackFor = Exception.class)
    public void rebuildFileIndex(Long kbId, Long fileId) {
        // 校验文件存在且已解析
        KbFileNode node = fileNodeService.getById(fileId);
        if (node == null || !kbId.equals(node.getKbId()) || !"file".equals(node.getNodeType())) {
            throw new RuntimeException("文件不存在");
        }
        if (!"parsed".equals(node.getParseStatus())) {
            throw new RuntimeException("文件未解析完成，无法重建索引");
        }
        // 查找最新成功的 parse task
        KbFileTask task = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getFileNodeId, fileId)
                .eq(KbFileTask::getStage, "parse")
                .eq(KbFileTask::getStatus, "success")
                .orderByDesc(KbFileTask::getId)
                .last("limit 1"));
        if (task == null) {
            throw new RuntimeException("未找到成功的解析任务");
        }
        // 重置索引状态
        task.setIndexSyncStatus("syncing");
        task.setErrorMsg(null);
        fileTaskMapper.updateById(task);
        node.setIndexStatus("indexing");
        fileNodeService.updateById(node);
        // 调用 rag-doc 重建索引
        try {
            retrievalEngineClient.rebuildFileIndex(task);
        } catch (Exception e) {
            task.setIndexSyncStatus("failed");
            task.setErrorMsg(truncate("索引服务调用失败: " + e.getMessage(), 2000));
            fileTaskMapper.updateById(task);
            node.setIndexStatus("failed");
            fileNodeService.updateById(node);
            throw new RuntimeException("索引服务调用失败: " + e.getMessage());
        }
    }

    private void markNodeIndexStatus(Long fileNodeId, String indexStatus, String indexGeneration) {
        if (fileNodeId == null) {
            return;
        }
        KbFileNode node = fileNodeService.getById(fileNodeId);
        if (node == null || "folder".equals(node.getNodeType())) {
            return;
        }
        node.setIndexStatus(indexStatus);
        if (!isBlank(indexGeneration)) {
            node.setCurrentIndexGeneration(indexGeneration.trim());
        }
        fileNodeService.updateById(node);
    }

    private void markNodeFailedIfLatest(KbFileTask task) {
        markNodeFailedIfLatest(task, task.getFileNodeId());
    }

    private void markNodeFailedIfLatest(KbFileTask task, Long fileNodeId) {
        if (fileNodeId == null || !isLatestTask(fileNodeId, task.getId())) {
            return;
        }
        KbFileNode node = fileNodeService.getById(fileNodeId);
        if (node == null || "folder".equals(node.getNodeType())) {
            return;
        }
        node.setParseStatus("failed");
        fileNodeService.updateById(node);
    }

    private boolean isLatestTask(Long fileNodeId, Long taskId) {
        KbFileTask latestTask = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getFileNodeId, fileNodeId)
                .eq(KbFileTask::getStage, "parse")
                .orderByDesc(KbFileTask::getId)
                .last("limit 1"));
        return latestTask != null && latestTask.getId() != null && latestTask.getId().equals(taskId);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }
}
