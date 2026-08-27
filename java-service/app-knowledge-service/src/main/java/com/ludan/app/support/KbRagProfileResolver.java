package com.ludan.app.support;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.config.ParseEngineProperties;
import com.ludan.app.config.RetrievalEngineProperties;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.entity.KbRetrievalStrategyConfig;
import com.ludan.app.mapper.KbRetrievalStrategyConfigMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

/**
 * 将知识库类型、检索策略与请求 options 统一解析为 app-rag-doc 的 profile / options。
 */
@Component
@RequiredArgsConstructor
public class KbRagProfileResolver {

    private final RetrievalEngineProperties retrievalEngineProperties;
    private final ParseEngineProperties parseEngineProperties;
    private final KbRetrievalStrategyConfigMapper retrievalStrategyConfigMapper;
    private final ObjectMapper objectMapper;

    /**
     * 组装检索 options：直接透传请求 options，不再注入 profile。
     * profile 由 rag-doc 侧自行管理。
     */
    public Map<String, Object> buildRetrieveOptions(KbKnowledgeBase kb, Map<String, Object> requestOptions) {
        Map<String, Object> options = new HashMap<>();
        if (requestOptions != null && !requestOptions.isEmpty()) {
            options.putAll(requestOptions);
        }
        // 不再向 rag-doc 传递 profile
        options.remove("profile");
        return options.isEmpty() ? null : options;
    }

    /**
     * 解析检索 profile（不含请求覆盖）。
     */
    public String resolveRetrieveProfile(KbKnowledgeBase kb) {
        String fromKb = normalizeKbTypeToProfile(kb == null ? null : kb.getType());
        if (StringUtils.hasText(fromKb)) {
            return fromKb;
        }
        String fromStrategy = profileFromRetrievalConfig(kb == null ? null : kb.getRetrievalConfigId());
        if (StringUtils.hasText(fromStrategy)) {
            return fromStrategy;
        }
        String configured = retrievalEngineProperties.getDefaultProfile();
        return StringUtils.hasText(configured) ? configured.trim() : "general_document";
    }

    /**
     * 解析解析任务 profile：model_profile JSON 优先，其次知识库 type，最后 parse-engine 默认。
     */
    public String resolveParseProfile(KbKnowledgeBase kb, String modelProfileJson) {
        String fromJson = profileFromModelProfileJson(modelProfileJson);
        if (StringUtils.hasText(fromJson)) {
            return fromJson;
        }
        String fromKb = normalizeKbTypeToProfile(kb == null ? null : kb.getType());
        if (StringUtils.hasText(fromKb)) {
            return fromKb;
        }
        String configured = parseEngineProperties.getDefaultProfile();
        return StringUtils.hasText(configured) ? configured.trim() : "auto";
    }

    private String profileFromModelProfileJson(String modelProfileJson) {
        if (!StringUtils.hasText(modelProfileJson)) {
            return null;
        }
        try {
            JsonNode root = objectMapper.readTree(modelProfileJson);
            String profile = readText(root, "profile");
            if (!StringUtils.hasText(profile)) {
                profile = readText(root.path("parse"), "profile");
            }
            return StringUtils.hasText(profile) ? profile.trim() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private String profileFromRetrievalConfig(String retrievalConfigId) {
        if (!StringUtils.hasText(retrievalConfigId)) {
            return null;
        }
        KbRetrievalStrategyConfig config = retrievalStrategyConfigMapper.selectById(retrievalConfigId.trim());
        if (config == null || !StringUtils.hasText(config.getConfigJson())) {
            return null;
        }
        try {
            JsonNode root = objectMapper.readTree(config.getConfigJson());
            return readText(root, "profile");
        } catch (Exception e) {
            return null;
        }
    }

    private String normalizeKbTypeToProfile(String kbType) {
        if (!StringUtils.hasText(kbType)) {
            return null;
        }
        return kbType.trim();
    }

    private String profileFromMap(Map<String, Object> options) {
        if (options == null || options.isEmpty()) {
            return null;
        }
        Object profile = options.get("profile");
        if (profile == null) {
            return null;
        }
        String text = profile.toString().trim();
        return text.isEmpty() ? null : text;
    }

    private String readText(JsonNode node, String fieldName) {
        if (node == null || node.isMissingNode() || node.isNull()) {
            return null;
        }
        JsonNode value = node.get(fieldName);
        if (value == null || value.isNull()) {
            return null;
        }
        String text = value.asText();
        return text == null || text.trim().isEmpty() ? null : text.trim();
    }
}
