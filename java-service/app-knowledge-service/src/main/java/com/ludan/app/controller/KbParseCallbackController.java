package com.ludan.app.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.central.common.model.Result;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.mapper.KbFileTaskMapper;
import com.ludan.app.service.impl.KbParseTaskStatusSyncService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 解析引擎回调接口（内部接口）
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/internal/platform")
@Api(tags = "内部-解析引擎回调")
@RequiredArgsConstructor
public class KbParseCallbackController {

    private final KbFileTaskMapper fileTaskMapper;
    private final KbParseTaskStatusSyncService parseTaskStatusSyncService;

    @ApiOperation(value = "解析回调")
    @PostMapping("/parse-callback")
    public Result<Void> parseCallback(@RequestBody Map<String, Object> body) {
        Long fileNodeId = resolveLong(body.get("file_node_id"));
        String stage = (String) body.get("stage");
        String status = (String) body.get("status");
        String parseGeneration = (String) body.get("parse_generation");
        String indexGeneration = (String) body.get("index_generation");
        String engineTaskId = (String) body.get("engine_task_id");
        String parseResultUrl = (String) body.get("parse_result_url");
        Integer chunkCount = resolveChunkCount(body);
        String errorMsg = (String) body.get("error_msg");

        KbFileTask task = resolveCallbackTask(body.get("task_id"), engineTaskId, fileNodeId);
        if (task == null) {
            log.warn("回调任务不存在: taskId={}, engineTaskId={}, fileNodeId={}",
                    body.get("task_id"), engineTaskId, fileNodeId);
            return Result.failed("任务不存在");
        }
        Long taskId = task.getId();
        if (fileNodeId == null) {
            fileNodeId = task.getFileNodeId();
        }

        parseTaskStatusSyncService.applyCallback(taskId, fileNodeId, stage, status, parseGeneration, indexGeneration,
                engineTaskId, parseResultUrl, chunkCount, errorMsg);

        log.info("解析回调处理完成: taskId={}, status={}", taskId, status);
        return Result.succeed(null, "回调处理成功");
    }

    private KbFileTask resolveCallbackTask(Object rawTaskId, String engineTaskId, Long fileNodeId) {
        Long taskId = resolveLongSafely(rawTaskId);
        if (taskId != null) {
            KbFileTask task = fileTaskMapper.selectById(taskId);
            if (task != null) {
                return task;
            }
        }
        LambdaQueryWrapper<KbFileTask> query = new LambdaQueryWrapper<>();
        if (engineTaskId != null && !engineTaskId.trim().isEmpty()) {
            query.eq(KbFileTask::getEngineTaskId, engineTaskId.trim());
            query.orderByDesc(KbFileTask::getCreateTime).last("LIMIT 1");
            KbFileTask task = fileTaskMapper.selectOne(query);
            if (task != null) {
                return task;
            }
        }
        if (fileNodeId == null) {
            return null;
        }
        return fileTaskMapper.selectOne(new LambdaQueryWrapper<KbFileTask>()
                .eq(KbFileTask::getFileNodeId, fileNodeId)
                .orderByDesc(KbFileTask::getCreateTime)
                .last("LIMIT 1"));
    }

    @ApiOperation(value = "索引完成回调")
    @PostMapping("/index-callback")
    public Result<Void> indexCallback(@RequestBody Map<String, Object> body) {
        Long kbId = resolveLong(body.get("kb_id"));
        Long fileNodeId = resolveLong(body.get("file_node_id"));
        String status = resolveString(body.get("status"));
        String indexGeneration = resolveString(body.get("index_generation"));
        Integer indexedChunks = resolveInteger(firstNonNull(body.get("indexed_chunks"), body.get("indexed_chunk_count")));
        String errorMsg = resolveString(firstNonNull(body.get("error_msg"), body.get("message")));

        if (kbId == null || fileNodeId == null) {
            return Result.failed("kb_id 和 file_node_id 不能为空");
        }
        if (status == null || status.trim().isEmpty()) {
            return Result.failed("status 不能为空");
        }

        boolean handled = parseTaskStatusSyncService.applyIndexCallback(
                kbId, fileNodeId, status, indexGeneration, indexedChunks, errorMsg);
        if (!handled) {
            log.warn("索引回调未找到匹配任务: kbId={}, fileNodeId={}, status={}", kbId, fileNodeId, status);
            return Result.failed("任务不存在");
        }

        log.info("索引回调处理完成: kbId={}, fileNodeId={}, status={}", kbId, fileNodeId, status);
        return Result.succeed(null, "回调处理成功");
    }

    private Integer resolveChunkCount(Map<String, Object> body) {
        Object chunkCount = body.get("chunk_count");
        if (chunkCount == null) {
            chunkCount = body.get("indexed_chunk_count");
        }
        return chunkCount == null ? 0 : Integer.valueOf(chunkCount.toString());
    }

    private Object firstNonNull(Object first, Object second) {
        return first != null ? first : second;
    }

    private String resolveString(Object value) {
        return value == null ? null : value.toString();
    }

    private Long resolveLong(Object value) {
        if (value == null || value.toString().trim().isEmpty()) {
            return null;
        }
        return Long.valueOf(value.toString());
    }

    private Long resolveLongSafely(Object value) {
        try {
            return resolveLong(value);
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private Integer resolveInteger(Object value) {
        if (value == null || value.toString().trim().isEmpty()) {
            return null;
        }
        return Integer.valueOf(value.toString());
    }
}
