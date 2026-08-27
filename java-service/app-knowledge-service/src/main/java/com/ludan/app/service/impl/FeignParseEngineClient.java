package com.ludan.app.service.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.config.ParseEngineProperties;
import com.ludan.app.dto.rag.RagParseFileRequest;
import com.ludan.app.dto.rag.RagParseFileResponse;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbFileTask;
import com.ludan.app.feign.AppRagDocParseClient;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbFileNodeMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.service.ParseEngineClient;
import com.ludan.app.support.KbRagProfileResolver;
import com.ludan.app.service.model.ParseTaskStatusSnapshot;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import javax.annotation.PostConstruct;
import java.util.HashMap;
import java.util.Map;

/**
 * 通过 Nacos/OpenFeign 调用 AI 引擎解析能力。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class FeignParseEngineClient implements ParseEngineClient {

    private final AppRagDocParseClient parseClient;
    private final ParseEngineProperties properties;
    private final ObjectMapper objectMapper;
    private final KbFileNodeMapper fileNodeMapper;
    private final KbKnowledgeBaseMapper knowledgeBaseMapper;
    private final KbRagProfileResolver ragProfileResolver;

    @PostConstruct
    public void init() {
        log.info("解析引擎客户端(Feign): serviceName={}, enabled={}",
                properties.getServiceName(), properties.isEnabled());
    }

    @Override
    public String submitParseTask(KbFileTask task, String modelProfileJson) {
        if (!properties.isEnabled()) {
            log.info("解析引擎调用已关闭，跳过提交: taskId={}", task.getId());
            return null;
        }
        RagParseFileRequest req = new RagParseFileRequest();
        req.setTaskId(task.getId());
        req.setKbId(task.getKbId());
        req.setFileNodeId(task.getFileNodeId());
        req.setFileId(resolveStorageFileId(task));
        req.setProfile(ragProfileResolver.resolveParseProfile(resolveKb(task.getKbId()), modelProfileJson));
        req.setParseGeneration(task.getParseGeneration());
        req.setIndexGeneration(task.getIndexGeneration());
        req.setEngineTaskId(String.valueOf(task.getId()));
        req.setParseStrategyConfigId(task.getParseStrategyConfigId());
        req.setModelProfile(parseJsonObject(modelProfileJson));
        req.setAsyncMode(true);
        req.setReturnPayload(false);
        if (Integer.valueOf(1).equals(task.getMultimodalEnabled())) {
            Map<String, Object> multimodal = new HashMap<>();
            multimodal.put("enabled", true);
            Map<String, Object> parseOptions = new HashMap<>();
            parseOptions.put("multimodal", multimodal);
            req.setParseOptions(parseOptions);
        }

        RagParseFileResponse resp = parseClient.submitParseFile(req);
        if (resp == null || !StringUtils.hasText(resp.getStatus())) {
            throw new RuntimeException("解析引擎响应为空");
        }
        if (!"accepted".equalsIgnoreCase(resp.getStatus()) && !"success".equalsIgnoreCase(resp.getStatus())) {
            throw new RuntimeException("解析引擎返回非成功状态: " + resp.getStatus());
        }
        String engineTaskId = StringUtils.hasText(resp.getEngineTaskId()) ? resp.getEngineTaskId() : resp.getTaskId();
        if (!StringUtils.hasText(engineTaskId)) {
            engineTaskId = String.valueOf(task.getId());
        }
        log.info("解析任务已提交: taskId={}, engineTaskId={}, kbId={}, fileNodeId={}",
                task.getId(), engineTaskId, task.getKbId(), task.getFileNodeId());
        return engineTaskId;
    }

    @Override
    public ParseTaskStatusSnapshot queryParseTaskStatus(KbFileTask task) {
        if (!properties.isEnabled() || task == null || task.getId() == null) {
            return null;
        }
        Map<String, Object> body = parseClient.queryParseTask(task.getId());
        if (body == null || body.isEmpty()) {
            return null;
        }
        JsonNode root = objectMapper.valueToTree(body);
        JsonNode data = root.has("data") ? root.path("data") : root;
        if (data == null || data.isMissingNode() || data.isNull()) {
            return null;
        }
        ParseTaskStatusSnapshot snapshot = new ParseTaskStatusSnapshot();
        snapshot.setTaskId(readLong(data, "task_id"));
        snapshot.setEngineTaskId(readText(data, "engine_task_id"));
        snapshot.setStage(readText(data, "stage"));
        snapshot.setStatus(readText(data, "status"));
        snapshot.setChunkCount(readInteger(data, "chunk_count", "indexed_chunk_count"));
        snapshot.setErrorMsg(readText(data, "error_msg"));
        return snapshot;
    }

    private KbKnowledgeBase resolveKb(Long kbId) {
        if (kbId == null) {
            return null;
        }
        return knowledgeBaseMapper.selectById(kbId);
    }

    private String resolveStorageFileId(KbFileTask task) {
        if (task == null || task.getFileNodeId() == null) {
            throw new RuntimeException("解析任务缺少 fileNodeId");
        }
        KbFileNode node = fileNodeMapper.selectById(task.getFileNodeId());
        if (node == null) {
            throw new RuntimeException("文件节点不存在: " + task.getFileNodeId());
        }
        if (!StringUtils.hasText(node.getFileId())) {
            throw new RuntimeException("文件节点缺少文件中心 file_id: " + task.getFileNodeId());
        }
        return node.getFileId().trim();
    }

    private Map<String, Object> parseJsonObject(String json) {
        if (!StringUtils.hasText(json)) {
            return null;
        }
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception e) {
            log.warn("model_profile 不是合法 JSON 对象，已跳过透传: {}", e.getMessage());
            return null;
        }
    }

    private String readText(JsonNode node, String fieldName) {
        JsonNode value = node == null ? null : node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }
        String text = value.asText();
        return text == null || text.trim().isEmpty() ? null : text.trim();
    }

    private Long readLong(JsonNode node, String fieldName) {
        JsonNode value = node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }
        return value.asLong();
    }

    private Integer readInteger(JsonNode node, String... fieldNames) {
        for (String fieldName : fieldNames) {
            JsonNode value = node.get(fieldName);
            if (value != null && !value.isNull()) {
                return value.asInt();
            }
        }
        return null;
    }
}
