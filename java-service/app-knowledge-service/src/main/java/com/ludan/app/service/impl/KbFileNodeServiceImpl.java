package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.dto.req.KbBatchCreateFileReqDTO;
import com.ludan.app.dto.resp.KbBatchCreateFileResultDTO;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbChunkMapper;
import com.ludan.app.mapper.KbChunkRevisionMapper;
import com.ludan.app.mapper.KbFileNodeMapper;
import com.ludan.app.mapper.KbFileTaskMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.service.KbFileNodeService;
import com.ludan.app.service.ParseEngineClient;
import com.ludan.app.service.RetrievalEngineClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 文件节点 Service 实现
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbFileNodeServiceImpl
        extends SuperServiceImpl<KbFileNodeMapper, KbFileNode>
        implements KbFileNodeService {

    private static final Pattern SHA_256_PATTERN = Pattern.compile("^[a-fA-F0-9]{64}$");
    private static final String PARSE_SERVICE_UNAVAILABLE_MESSAGE = "解析服务暂不可用，请稍后重试或联系管理员";
    private static final String PARSE_TASK_SUBMIT_FAILED_MESSAGE = "解析任务提交失败，请稍后重试或联系管理员";

    private final KbFileTaskMapper fileTaskMapper;
    private final KbKnowledgeBaseMapper knowledgeBaseMapper;
    private final KbChunkMapper chunkMapper;
    private final KbChunkRevisionMapper chunkRevisionMapper;
    private final ParseEngineClient parseEngineClient;
    private final RetrievalEngineClient retrievalEngineClient;

    @Override
    public List<KbFileNode> getFileTree(Long kbId) {
        Map<Long, ChunkAuditStats> chunkAuditStats = loadChunkAuditStats(kbId);
        Map<Long, KbFileTask> latestParseTasks = loadLatestParseTasks(kbId);
        List<KbFileNode> roots = baseMapper.selectByKbId(kbId, null);
        for (KbFileNode node : roots) {
            normalizeFileNodeName(node);
            applyChunkAuditStatus(node, chunkAuditStats);
            applyParseTaskSnapshot(node, latestParseTasks);
            if ("folder".equals(node.getNodeType())) {
                loadChildren(kbId, node, chunkAuditStats, latestParseTasks);
            }
        }
        return roots;
    }

    /**
     * 递归加载文件夹子节点（使用 @TableField(exist=false) 的 children 不写入DB）
     */
    private void loadChildren(Long kbId, KbFileNode parent, Map<Long, ChunkAuditStats> chunkAuditStats,
                              Map<Long, KbFileTask> latestParseTasks) {
        List<KbFileNode> children = baseMapper.selectByKbId(kbId, parent.getId());
        for (KbFileNode child : children) {
            normalizeFileNodeName(child);
            applyChunkAuditStatus(child, chunkAuditStats);
            applyParseTaskSnapshot(child, latestParseTasks);
            if ("folder".equals(child.getNodeType())) {
                loadChildren(kbId, child, chunkAuditStats, latestParseTasks);
            }
        }
        parent.setChildren(children);
    }

    private Map<Long, ChunkAuditStats> loadChunkAuditStats(Long kbId) {
        List<Map<String, Object>> rows = baseMapper.selectPendingChunkCounts(kbId);
        Map<Long, ChunkAuditStats> statsMap = new HashMap<>();
        for (Map<String, Object> row : rows) {
            Long fileNodeId = toLong(row.get("fileNodeId"));
            if (fileNodeId != null) {
                ChunkAuditStats stats = new ChunkAuditStats();
                stats.totalChunkCount = safeInteger(row.get("totalChunkCount"));
                stats.pendingChunkCount = safeInteger(row.get("pendingChunkCount"));
                stats.approvedChunkCount = safeInteger(row.get("approvedChunkCount"));
                stats.rejectedChunkCount = safeInteger(row.get("rejectedChunkCount"));
                statsMap.put(fileNodeId, stats);
            }
        }
        return statsMap;
    }

    private Map<Long, KbFileTask> loadLatestParseTasks(Long kbId) {
        List<KbFileTask> tasks = fileTaskMapper.selectList(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getKbId, kbId)
                .eq(KbFileTask::getStage, "parse")
                .orderByDesc(KbFileTask::getId));
        Map<Long, KbFileTask> latestTasks = new HashMap<>();
        for (KbFileTask task : tasks) {
            if (task != null && task.getFileNodeId() != null && !latestTasks.containsKey(task.getFileNodeId())) {
                latestTasks.put(task.getFileNodeId(), task);
            }
        }
        return latestTasks;
    }

    private void applyChunkAuditStatus(KbFileNode node, Map<Long, ChunkAuditStats> chunkAuditStats) {
        ChunkAuditStats stats = chunkAuditStats.getOrDefault(node.getId(), ChunkAuditStats.EMPTY);
        node.setPendingChunkCount(stats.pendingChunkCount);
        if (!"file".equals(node.getNodeType()) || stats.totalChunkCount <= 0) {
            return;
        }
        if (stats.pendingChunkCount > 0) {
            node.setAuditStatus("pending");
        } else if (stats.approvedChunkCount > 0 && stats.rejectedChunkCount > 0) {
            node.setAuditStatus("partially_approved");
        } else if (stats.approvedChunkCount > 0) {
            node.setAuditStatus("approved");
        } else if (stats.rejectedChunkCount > 0) {
            node.setAuditStatus("rejected");
        }
    }

    private void applyParseTaskSnapshot(KbFileNode node, Map<Long, KbFileTask> latestParseTasks) {
        if (node == null || !"file".equals(node.getNodeType())) {
            return;
        }
        KbFileTask latestTask = latestParseTasks.get(node.getId());
        if (latestTask == null || !"failed".equals(latestTask.getStatus())) {
            node.setParseErrorMsg(null);
            return;
        }
        node.setParseErrorMsg(toUserParseErrorMessage(latestTask.getErrorMsg()));
    }

    private Long toLong(Object value) {
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        return value == null ? null : Long.valueOf(value.toString());
    }

    private Integer toInteger(Object value) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return value == null ? null : Integer.valueOf(value.toString());
    }

    private int safeInteger(Object value) {
        Integer integer = toInteger(value);
        return integer == null ? 0 : integer;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public KbFileNode createFileNode(Long kbId, Long parentId, String fileId, String fileName, String originalName,
                                     Long fileSize, String mimeType, String fileExt, String fileHash,
                                     String parseStrategyConfigId, Integer multimodalEnabled) {
        validateParentFolder(kbId, parentId);
        String actualParseStrategyConfigId = resolveParseStrategyConfigId(kbId, parseStrategyConfigId);
        KbFileNode node = new KbFileNode();
        node.setKbId(kbId);
        node.setParentId(parentId);
        node.setNodeType("file");
        node.setName(normalizeFileName(fileName));
        node.setOriginalName(normalizeFileName(originalName));
        node.setFileId(fileId);
        node.setFileSize(fileSize);
        node.setMimeType(mimeType);
        node.setFileExt(fileExt);
        node.setFileHash(fileHash);
        node.setParseStrategyConfigId(actualParseStrategyConfigId);
        node.setMultimodalEnabled(multimodalEnabled);
        node.setParseStatus("none");
        node.setIndexStatus("none");
        this.save(node);

        KbFileTask task = createPendingParseTask(kbId, node.getId(), actualParseStrategyConfigId, 1, multimodalEnabled);

        // 更新文件节点解析状态
        node.setParseStatus("parsing");
        this.updateById(node);

        // 提交到解析引擎（异步回调，事务提交后执行）
        submitToParseEngine(task);

        return node;
    }

    @Override
    public List<KbBatchCreateFileResultDTO> batchCreateFileNodes(Long kbId, Long parentId, String parseStrategyConfigId,
                                                                 List<KbBatchCreateFileReqDTO.UploadedFileItem> files) {
        if (files == null || files.isEmpty()) {
            throw new RuntimeException("上传文件不能为空");
        }
        validateParentFolder(kbId, parentId);

        List<KbBatchCreateFileResultDTO> results = new ArrayList<>();
        for (KbBatchCreateFileReqDTO.UploadedFileItem file : files) {
            String fileId = file == null ? null : file.getFileId();
            String fileName = resolveResultFileName(file);
            String fileHash = file == null ? null : file.getFileHash();
            try {
                if (file == null || isBlank(file.getFileId())) {
                    results.add(KbBatchCreateFileResultDTO.failed(fileId, fileName, fileHash, "fileId 不能为空"));
                    continue;
                }

                String normalizedFileHash = normalizeFileHash(file.getFileHash());
                if (isFileExists(kbId, file.getFileId(), normalizedFileHash)) {
                    results.add(KbBatchCreateFileResultDTO.duplicate(file.getFileId(), fileName, normalizedFileHash));
                    continue;
                }

                createFileNode(kbId, parentId, file.getFileId(), fileName, file.getOriginalName(), file.getFileSize(),
                        file.getMimeType(), file.getFileExt(), normalizedFileHash, parseStrategyConfigId,
                        toFlag(file.getMultimodalEnabled()));
                results.add(KbBatchCreateFileResultDTO.success(file.getFileId(), fileName, normalizedFileHash));
            } catch (RuntimeException e) {
                log.warn("文件入库失败，已跳过当前文件: kbId={}, fileId={}, fileName={}, message={}",
                        kbId, fileId, fileName, e.getMessage());
                results.add(KbBatchCreateFileResultDTO.failed(fileId, fileName, fileHash, e.getMessage()));
            }
        }
        return results;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public KbFileNode createFolderNode(Long kbId, Long parentId, String folderName) {
        if (isBlank(folderName)) {
            throw new RuntimeException("文件夹名称不能为空");
        }
        validateParentFolder(kbId, parentId);
        KbFileNode node = new KbFileNode();
        node.setKbId(kbId);
        node.setParentId(parentId);
        node.setNodeType("folder");
        node.setName(normalizeFileName(folderName));
        node.setParseStatus("none");
        node.setIndexStatus("none");
        this.save(node);
        return node;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void renameNode(Long kbId, Long fileNodeId, String nodeName) {
        if (isBlank(nodeName)) {
            throw new RuntimeException("节点名称不能为空");
        }
        KbFileNode node = this.getById(fileNodeId);
        if (node == null || !kbId.equals(node.getKbId())) {
            throw new RuntimeException("文件节点不存在");
        }
        node.setName(normalizeFileName(nodeName));
        this.updateById(node);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void moveNode(Long kbId, Long fileNodeId, Long targetParentId) {
        KbFileNode node = this.getById(fileNodeId);
        if (node == null || !kbId.equals(node.getKbId())) {
            throw new RuntimeException("文件节点不存在");
        }
        if (targetParentId != null) {
            KbFileNode targetParent = this.getById(targetParentId);
            if (targetParent == null || !kbId.equals(targetParent.getKbId())) {
                throw new RuntimeException("目标目录不存在");
            }
            if (!"folder".equals(targetParent.getNodeType())) {
                throw new RuntimeException("目标节点不是文件夹");
            }
            if (fileNodeId.equals(targetParentId) || isDescendantFolder(fileNodeId, targetParentId)) {
                throw new RuntimeException("不能移动到自身或子目录下");
            }
        }
        node.setParentId(targetParentId);
        this.updateById(node);
    }

    /**
     * 删除文件/文件夹：硬删节点及下属 Chunk/Revision，并尽力清理文件向量索引。
     * <p>
     * 索引删除失败只记录告警，不回滚库表删除（与 QA 删除策略一致）。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteNode(Long kbId, Long fileNodeId) {
        KbFileNode node = this.getById(fileNodeId);
        if (node == null || !kbId.equals(node.getKbId())) {
            throw new RuntimeException("文件节点不存在");
        }

        List<Long> deleteIds = new ArrayList<>();
        collectNodeIds(kbId, fileNodeId, deleteIds);
        if (deleteIds.isEmpty()) {
            return;
        }

        List<Long> fileIds = new ArrayList<>();
        List<KbFileNode> nodes = this.listByIds(deleteIds);
        if (nodes != null) {
            for (KbFileNode n : nodes) {
                if (n != null && "file".equals(n.getNodeType())) {
                    fileIds.add(n.getId());
                }
            }
        }

        if (!fileIds.isEmpty()) {
            chunkRevisionMapper.physicalDeleteByFileNodeIds(fileIds);
            chunkMapper.physicalDeleteByFileNodeIds(fileIds);
        }
        baseMapper.physicalDeleteByIds(deleteIds);

        for (Long fileId : fileIds) {
            try {
                retrievalEngineClient.deleteFileIndex(kbId, fileId);
            } catch (Exception e) {
                log.warn("删除文件后索引同步失败: kbId={}, fileNodeId={}, msg={}",
                        kbId, fileId, e.getMessage());
            }
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void triggerReparse(Long kbId, Long fileNodeId) {
        KbFileNode node = this.getById(fileNodeId);
        if (node == null || !kbId.equals(node.getKbId()) || !"file".equals(node.getNodeType())) {
            throw new RuntimeException("文件不存在");
        }

        // 计算新代际序号
        String currentGen = node.getCurrentParseGeneration();
        int seq = 1;
        if (currentGen != null && currentGen.startsWith("file_")) {
            String[] parts = currentGen.split("_");
            if (parts.length == 3) {
                seq = Integer.parseInt(parts[2]) + 1;
            }
        }
        String newGeneration = "file_" + fileNodeId + "_" + seq;

        // 更新文件节点状态
        node.setParseStatus("parsing");
        node.setIndexStatus("none");
        node.setCurrentParseGeneration(null);
        node.setCurrentIndexGeneration(null);
        this.updateById(node);

        String actualParseStrategyConfigId = resolveParseStrategyConfigId(kbId, node.getParseStrategyConfigId());
        node.setParseStrategyConfigId(actualParseStrategyConfigId);
        this.updateById(node);

        KbFileTask task = createPendingParseTask(kbId, fileNodeId, actualParseStrategyConfigId, seq,
                node.getMultimodalEnabled());

        // 提交到解析引擎
        submitToParseEngine(task);

        log.info("触发重解析: fileNodeId={}, generation={}", fileNodeId, newGeneration);
    }

    @Override
    public int triggerReparseAll(Long kbId) {
        // @TableLogic 自动追加 del_flag = 0
        List<KbFileNode> fileNodes = this.list(
                new LambdaQueryWrapper<KbFileNode>()
                        .eq(KbFileNode::getKbId, kbId)
                        .eq(KbFileNode::getNodeType, "file"));
        if (fileNodes == null || fileNodes.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (KbFileNode node : fileNodes) {
            try {
                triggerReparse(kbId, node.getId());
                count++;
            } catch (Exception e) {
                log.warn("重新解析失败: fileNodeId={}, error={}", node.getId(), e.getMessage());
            }
        }
        log.info("重新解析全部: kbId={}, total={}, success={}", kbId, fileNodes.size(), count);
        return count;
    }

    @Override
    public int triggerReparseAll(Long kbId, Long folderId) {
        // 校验目录存在且属于该知识库
        KbFileNode folder = this.getById(folderId);
        if (folder == null || !kbId.equals(folder.getKbId()) || !"folder".equals(folder.getNodeType())) {
            throw new RuntimeException("目录不存在");
        }
        // 递归收集所有子目录 ID（含自身）
        Set<Long> folderIds = new HashSet<>();
        collectFolderIds(kbId, folderId, folderIds);

        // 查询这些目录下所有 file 节点
        List<KbFileNode> fileNodes = this.list(
                new LambdaQueryWrapper<KbFileNode>()
                        .eq(KbFileNode::getKbId, kbId)
                        .eq(KbFileNode::getNodeType, "file")
                        .in(KbFileNode::getParentId, folderIds));
        if (fileNodes == null || fileNodes.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (KbFileNode node : fileNodes) {
            try {
                triggerReparse(kbId, node.getId());
                count++;
            } catch (Exception e) {
                log.warn("重新解析失败: fileNodeId={}, error={}", node.getId(), e.getMessage());
            }
        }
        log.info("按目录重新解析: kbId={}, folderId={}, total={}, success={}", kbId, folderId, fileNodes.size(), count);
        return count;
    }

    private void collectFolderIds(Long kbId, Long parentId, Set<Long> collected) {
        if (!collected.add(parentId)) return;
        List<KbFileNode> children = this.list(
                new LambdaQueryWrapper<KbFileNode>()
                        .eq(KbFileNode::getKbId, kbId)
                        .eq(KbFileNode::getParentId, parentId)
                        .eq(KbFileNode::getNodeType, "folder"));
        for (KbFileNode child : children) {
            collectFolderIds(kbId, child.getId(), collected);
        }
    }

    /**
     * 提交解析任务到解析引擎，回写 engineTaskId
     */
    private void submitToParseEngine(KbFileTask task) {
        try {
            String engineTaskId = parseEngineClient.submitParseTask(task, task.getModelProfile());
            if (isBlank(engineTaskId)) {
                markParseSubmitFailed(task, "解析引擎未返回 engineTaskId");
                return;
            }

            task.setEngineTaskId(engineTaskId);
            task.setStatus("processing");
            task.setErrorMsg(null);
            fileTaskMapper.updateById(task);
        } catch (Exception e) {
            log.error("提交解析引擎异常: taskId={}", task.getId(), e);
            markParseSubmitFailed(task, toUserParseErrorMessage(e.getMessage()));
        }
    }

    private void markParseSubmitFailed(KbFileTask task, String errorMsg) {
        task.setStatus("failed");
        task.setErrorMsg(truncate(errorMsg, 2000));
        fileTaskMapper.updateById(task);

        KbFileNode node = this.getById(task.getFileNodeId());
        if (node != null) {
            node.setParseStatus("failed");
            this.updateById(node);
        }
    }

    /**
     * 创建待解析任务并落库。
     */
    private KbFileTask createPendingParseTask(Long kbId, Long fileNodeId, String parseStrategyConfigId, int generationSeq,
                                             Integer multimodalEnabled) {
        String parseGeneration = "file_" + fileNodeId + "_" + generationSeq;
        KbFileTask task = fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getKbId, kbId)
                .eq(KbFileTask::getFileNodeId, fileNodeId)
                .last("limit 1"));
        if (task == null) {
            task = new KbFileTask();
            task.setKbId(kbId);
            task.setFileNodeId(fileNodeId);
        }
        task.setStage("parse");
        task.setStatus("pending");
        task.setErrorMsg(null);
        task.setParseResultUrl(null);
        task.setIndexedChunkCount(0);
        task.setIndexSyncStatus("none");
        task.setParseGeneration(parseGeneration);
        task.setIndexGeneration(parseGeneration);
        task.setEngineTaskId(null);
        task.setParseStrategyConfigId(parseStrategyConfigId);
        task.setModelProfile(resolveModelProfile(kbId));
        task.setMultimodalEnabled(multimodalEnabled);
        if (task.getId() == null) {
            fileTaskMapper.insert(task);
        } else {
            fileTaskMapper.updateById(task);
        }
        return task;
    }

    private String resolveModelProfile(Long kbId) {
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        return kb == null ? null : kb.getModelProfile();
    }

    /**
     * 上传未指定解析策略时，使用知识库默认解析策略。
     */
    private String resolveParseStrategyConfigId(Long kbId, String parseStrategyConfigId) {
        if (!isBlank(parseStrategyConfigId)) {
            return parseStrategyConfigId.trim();
        }
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        return kb == null || isBlank(kb.getParseStrategyConfigId()) ? null : kb.getParseStrategyConfigId();
    }

    /**
     * 文件 hash 是 KB 侧去重键，必须是有效 SHA-256，避免空值绕过去重。
     * 空值返回 null（可选化），非空但格式不合法则抛异常。
     */
    private String normalizeFileHash(String fileHash) {
        if (isBlank(fileHash)) {
            return null;
        }
        String normalizedFileHash = fileHash.trim().toLowerCase(Locale.ROOT);
        if (!SHA_256_PATTERN.matcher(normalizedFileHash).matches()) {
            throw new RuntimeException("文件 Hash 格式不合法");
        }
        return normalizedFileHash;
    }

    /**
     * 同一知识库内，同一内容 hash 只允许入库一次；fileId 作为对象存储重复提交的兜底保护。
     * fileHash 为 null 时跳过 hash 去重，仅用 fileId 去重。
     */
    private boolean isFileExists(Long kbId, String fileId, String fileHash) {
        if (fileHash != null) {
            if (this.getOne(new LambdaQueryWrapper<KbFileNode>()
                    .eq(KbFileNode::getKbId, kbId)
                    .eq(KbFileNode::getFileHash, fileHash)
                    .eq(KbFileNode::getNodeType, "file"), false) != null) {
                return true;
            }
        }

        return this.getOne(new LambdaQueryWrapper<KbFileNode>()
                .eq(KbFileNode::getKbId, kbId)
                .eq(KbFileNode::getFileId, fileId)
                .eq(KbFileNode::getNodeType, "file"), false) != null;
    }

    private String resolveResultFileName(KbBatchCreateFileReqDTO.UploadedFileItem file) {
        if (file == null) {
            return null;
        }
        return normalizeFileName(isBlank(file.getFileName()) ? file.getOriginalName() : file.getFileName());
    }

    private Integer toFlag(Boolean enabled) {
        return enabled == null ? null : (enabled ? 1 : 0);
    }

    private void normalizeFileNodeName(KbFileNode node) {
        if (node == null) {
            return;
        }
        node.setName(normalizeFileName(node.getName()));
        node.setOriginalName(normalizeFileName(node.getOriginalName()));
    }

    static String normalizeFileName(String fileName) {
        if (fileName == null) {
            return null;
        }
        return decodePercentEncoded(fileName.trim());
    }

    private static String decodePercentEncoded(String value) {
        if (value.indexOf('%') < 0) {
            return value;
        }
        StringBuilder decoded = new StringBuilder(value.length());
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int index = 0;
        while (index < value.length()) {
            char current = value.charAt(index);
            if (current == '%' && index + 2 < value.length()) {
                int hi = Character.digit(value.charAt(index + 1), 16);
                int lo = Character.digit(value.charAt(index + 2), 16);
                if (hi >= 0 && lo >= 0) {
                    bytes.write((hi << 4) + lo);
                    index += 3;
                    continue;
                }
            }
            flushDecodedBytes(decoded, bytes);
            decoded.append(current);
            index += 1;
        }
        flushDecodedBytes(decoded, bytes);
        return decoded.toString();
    }

    private static void flushDecodedBytes(StringBuilder decoded, ByteArrayOutputStream bytes) {
        if (bytes.size() == 0) {
            return;
        }
        decoded.append(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
        bytes.reset();
    }

    static String toUserParseErrorMessage(String errorMsg) {
        if (errorMsg == null || errorMsg.trim().isEmpty()) {
            return PARSE_TASK_SUBMIT_FAILED_MESSAGE;
        }
        String lowerErrorMsg = errorMsg.toLowerCase(Locale.ROOT);
        if (lowerErrorMsg.contains("load balancer does not have available server")
                || lowerErrorMsg.contains("no instances available")
                || lowerErrorMsg.contains("connection refused")
                || lowerErrorMsg.contains("connect timed out")) {
            return PARSE_SERVICE_UNAVAILABLE_MESSAGE;
        }
        if (lowerErrorMsg.contains("clientexception")
                || lowerErrorMsg.contains("feign")
                || lowerErrorMsg.contains("java.")
                || lowerErrorMsg.contains("runtimeexception")) {
            return PARSE_TASK_SUBMIT_FAILED_MESSAGE;
        }
        return errorMsg.trim();
    }

    /**
     * 校验父节点存在且属于当前知识库。
     */
    private void validateParentFolder(Long kbId, Long parentId) {
        if (parentId == null) {
            return;
        }
        KbFileNode parent = this.getById(parentId);
        if (parent == null || !kbId.equals(parent.getKbId()) || !"folder".equals(parent.getNodeType())) {
            throw new RuntimeException("父目录不存在");
        }
    }

    /**
     * 递归收集要删除的节点，避免删除文件夹后留下孤儿节点。
     */
    private void collectNodeIds(Long kbId, Long fileNodeId, List<Long> ids) {
        ids.add(fileNodeId);
        List<KbFileNode> children = baseMapper.selectByKbId(kbId, fileNodeId);
        for (KbFileNode child : children) {
            collectNodeIds(kbId, child.getId(), ids);
        }
    }

    /**
     * 判断字符串是否为空白。
     */
    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    /**
     * 判断目标目录是否是当前文件夹的子孙节点，避免形成环形目录。
     */
    private boolean isDescendantFolder(Long folderId, Long targetFolderId) {
        KbFileNode current = this.getById(targetFolderId);
        while (current != null && current.getParentId() != null) {
            if (folderId.equals(current.getParentId())) {
                return true;
            }
            current = this.getById(current.getParentId());
        }
        return false;
    }

    private static class ChunkAuditStats {
        private static final ChunkAuditStats EMPTY = new ChunkAuditStats();

        private int totalChunkCount;
        private int pendingChunkCount;
        private int approvedChunkCount;
        private int rejectedChunkCount;
    }
}
