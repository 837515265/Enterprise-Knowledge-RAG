package com.ludan.app.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.config.LlmProperties;
import com.ludan.app.service.SiliconFlowChatClient;
import com.ludan.proxy.model.ModelInfo;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;

/**
 * 基于 HttpURLConnection 的 SiliconFlow 流式客户端。
 *
 * @author ludan
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HttpSiliconFlowChatClient implements SiliconFlowChatClient {

    @Value("${common-inner-proxy.streamUrl}")
    private String streamProxyUrl;

    private final LlmProperties properties;
    private final ObjectMapper objectMapper;
    private final RestTemplate loadBalancedStreamRestTemplate;

    @Override
    public void streamChat(String model, List<Map<String, String>> messages, boolean enableThinking,
                           Integer thinkingBudget, BiConsumer<String, String> onDelta) {
        try {
            doStreamChat(model, messages, enableThinking, thinkingBudget, true, onDelta);
        } catch (RuntimeException e) {
            if (isThinkingParamError(e.getMessage())) {
                log.warn("当前模型不支持思考参数，自动降级为普通回答: {}", e.getMessage());
                doStreamChat(model, messages, false, null, false, onDelta);
                return;
            }
            throw e;
        }
    }

    private void doStreamChat(String model, List<Map<String, String>> messages, boolean enableThinking,
                              Integer thinkingBudget, boolean sendThinkingParam, BiConsumer<String, String> onDelta) {
        try {
            String actualModel = isBlank(model) ? properties.getDefaultModel() : model.trim();
            if (isBlank(actualModel)) {
                throw new RuntimeException("未配置默认对话模型，请设置 llm.default-model 或知识库 model_profile.chat.model");
            }

            Map<String, Object> body = new HashMap<>(4);
            body.put("model", actualModel);
            body.put("messages", messages);
            body.put("stream", true);
            if (sendThinkingParam) {
                body.put("enable_thinking", enableThinking);
            }
            if (sendThinkingParam && enableThinking && thinkingBudget != null && thinkingBudget > 0) {
                body.put("thinking_budget", thinkingBudget);
            }
            if (!isBlank(properties.getApiKey())) {
                body.put("api_key", properties.getApiKey());
            }

            log.info("new-api代理调用开始: model={}, thirdAppId={}, thirdInterfaceId={}, thirdUrl={}, messageCount={}, enableThinking={}, thinkingBudget={}, sendThinkingParam={}",
                    actualModel, properties.getThirdAppId(), properties.getThirdInterfaceId(), properties.getThirdUrl(),
                    messages == null ? 0 : messages.size(), enableThinking, thinkingBudget, sendThinkingParam);
            ModelInfo modelInfo = buildModelInfo(body);
            loadBalancedStreamRestTemplate.execute(
                    streamProxyUrl,
                    HttpMethod.POST,
                    request -> {
                        request.getHeaders().setContentType(MediaType.APPLICATION_JSON);
                        request.getHeaders().setAccept(Collections.singletonList(MediaType.TEXT_EVENT_STREAM));
                        request.getHeaders().setCacheControl(CacheControl.noCache());
                        objectMapper.writeValue(request.getBody(), modelInfo);
                    },
                    response -> {
                        try (InputStream inputStream = response.getBody();
                             BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
                            String line;
                            while ((line = reader.readLine()) != null) {
                                parseAndEmitSseLine(line, enableThinking, onDelta);
                            }
                        }
                        return null;
                    }
            );
        } catch (Exception e) {
            log.error("new-api代理调用失败: {}", e.getMessage(), e);
            throw new RuntimeException(e.getMessage(), e);
        }
    }

    /**
     * 组装内部代理调用参数。
     */
    private ModelInfo buildModelInfo(Map<String, Object> body) {
        ModelInfo modelInfo = new ModelInfo();
        modelInfo.setData(body);
        modelInfo.setThirdAppId(properties.getThirdAppId());
        modelInfo.setThirdInterfaceId(properties.getThirdInterfaceId());
        modelInfo.setApplyAppId(properties.getApplyAppId());
        modelInfo.setThirdUrl(properties.getThirdUrl());
        modelInfo.setMethodType("POST");
        modelInfo.setContentType(MediaType.APPLICATION_JSON_VALUE);
        if (!isBlank(properties.getApiKey())) {
            Map<String, String> headerMap = new LinkedHashMap<>();
            headerMap.put(HttpHeaders.ACCEPT, MediaType.TEXT_EVENT_STREAM_VALUE);
            headerMap.put(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE);
            headerMap.put("Authorization", "Bearer " + properties.getApiKey());
            modelInfo.setHeaderMap(headerMap);
        }
        return modelInfo;
    }

    private void parseAndEmitSseLine(String line, boolean enableThinking, BiConsumer<String, String> onDelta) {
        if (isBlank(line)) {
            return;
        }
        parseAndEmitSseText(line + "\n", enableThinking, onDelta);
    }

    /**
     * 解析 SSE 文本并回调增量 token。
     */
    private void parseAndEmitSseText(String rawText, boolean enableThinking, BiConsumer<String, String> onDelta) {
        String[] lines = rawText.split("\\r?\\n");
        for (String line : lines) {
            if (isBlank(line) || !line.startsWith("data:")) {
                continue;
            }
            String chunk = line.substring(5).trim();
            if ("[DONE]".equals(chunk) || isBlank(chunk)) {
                continue;
            }
            JsonNode node;
            try {
                node = objectMapper.readTree(chunk);
            } catch (Exception parseEx) {
                log.warn("解析代理SSE分片失败，按纯文本透传: {}", parseEx.getMessage());
                onDelta.accept("content", chunk);
                continue;
            }

            String errorMessage = getText(node.path("error"), "message");
            if (!isBlank(errorMessage)) {
                throw new RuntimeException(errorMessage);
            }
            errorMessage = readProxyErrorMessage(node);
            if (!isBlank(errorMessage)) {
                throw new RuntimeException(errorMessage);
            }
            JsonNode choices = node.path("choices");
            if (!choices.isArray() || choices.size() == 0) {
                continue;
            }
            JsonNode delta = choices.get(0).path("delta");
            String reasoning = getText(delta, "reasoning_content");
            if (enableThinking && !isBlank(reasoning)) {
                onDelta.accept("reasoning", reasoning);
            }
            String content = getText(delta, "content");
            if (!isBlank(content)) {
                onDelta.accept("content", content);
            }
        }
    }

    private String readProxyErrorMessage(JsonNode node) {
        Integer code = readCode(node);
        if (code == null || code == 0 || code == 200) {
            return null;
        }
        String message = getText(node, "resp_msg");
        if (isBlank(message)) {
            message = getText(node, "msg");
        }
        if (isBlank(message)) {
            message = getText(node, "message");
        }
        if (isBlank(message)) {
            message = readNestedErrorMessage(node.path("datas"));
        }
        if (isBlank(message)) {
            message = readNestedErrorMessage(node.path("data"));
        }
        if (isBlank(message)) {
            message = readNestedErrorMessage(node.path("result"));
        }
        return message;
    }

    private Integer readCode(JsonNode node) {
        JsonNode codeNode = node.path("resp_code");
        if (codeNode.isMissingNode() || codeNode.isNull()) {
            codeNode = node.path("code");
        }
        if (codeNode.isMissingNode() || codeNode.isNull()) {
            return null;
        }
        if (codeNode.isInt()) {
            return codeNode.asInt();
        }
        try {
            return Integer.parseInt(codeNode.asText());
        } catch (Exception ignored) {
            return null;
        }
    }

    private String readNestedErrorMessage(JsonNode payload) {
        if (payload == null || payload.isMissingNode() || payload.isNull()) {
            return null;
        }
        try {
            JsonNode node = payload.isTextual() ? objectMapper.readTree(payload.asText()) : payload;
            String message = getText(node.path("error"), "message");
            if (!isBlank(message)) {
                return message;
            }
            return getText(node, "message");
        } catch (Exception e) {
            return null;
        }
    }

    private boolean isThinkingParamError(String message) {
        if (message == null) {
            return false;
        }
        String lower = message.toLowerCase();
        return lower.contains("enable_thinking")
                || lower.contains("thinking_budget")
                || lower.contains("unsupported")
                || lower.contains("not support");
    }

    private String getText(JsonNode node, String fieldName) {
        JsonNode field = node.get(fieldName);
        return field == null || field.isNull() ? null : field.asText();
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
