package com.ludan.app.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.config.ParseEngineProperties;
import com.ludan.app.feign.AppRagDocParseClient;
import com.ludan.app.service.KbParseTaskQueryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * 通过 Feign 转发 app-rag-doc 解析任务列表查询。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbParseTaskQueryServiceImpl implements KbParseTaskQueryService {

    private final AppRagDocParseClient parseClient;
    private final ParseEngineProperties parseEngineProperties;
    private final ObjectMapper objectMapper;

    @Override
    public List<Map<String, Object>> listParseTasks(String status, Long kbId, Long fileNodeId, Integer limit) {
        if (!parseEngineProperties.isEnabled()) {
            log.info("解析引擎调用已关闭，返回空任务列表");
            return Collections.emptyList();
        }

        Map<String, Object> params = new HashMap<>();
        if (StringUtils.hasText(status)) {
            params.put("status", status.trim());
        }
        if (kbId != null) {
            params.put("kb_id", kbId);
        }
        if (fileNodeId != null) {
            params.put("file_node_id", fileNodeId);
        }
        if (limit != null) {
            params.put("limit", Math.min(100, Math.max(1, limit)));
        }

        try {
            Object body = parseClient.listParseTasks(params);
            return extractTaskList(body);
        } catch (Exception e) {
            log.error("查询解析任务列表失败: params={}, error={}", params, e.getMessage(), e);
            throw new RuntimeException("查询解析任务列表失败: " + e.getMessage(), e);
        }
    }

    private List<Map<String, Object>> extractTaskList(Object body) {
        if (body == null) {
            return Collections.emptyList();
        }
        JsonNode root = objectMapper.valueToTree(body);
        if (root.isArray()) {
            return toMapList(root);
        }
        for (String field : new String[]{"data", "datas", "records", "tasks", "items"}) {
            JsonNode node = root.get(field);
            if (node != null && node.isArray()) {
                return toMapList(node);
            }
        }
        return Collections.emptyList();
    }

    private List<Map<String, Object>> toMapList(JsonNode arrayNode) {
        List<Map<String, Object>> list = new ArrayList<>();
        Iterator<JsonNode> it = arrayNode.elements();
        while (it.hasNext()) {
            JsonNode item = it.next();
            if (item != null && item.isObject()) {
                list.add(objectMapper.convertValue(item, Map.class));
            }
        }
        return list;
    }
}
