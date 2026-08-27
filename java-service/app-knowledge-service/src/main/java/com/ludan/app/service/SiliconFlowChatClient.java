package com.ludan.app.service;

import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;

/**
 * SiliconFlow Chat Completions 流式客户端
 *
 * @author ludan
 */
public interface SiliconFlowChatClient {

    /**
     * 以流式方式调用大模型，并将增量内容回调给调用方。
     */
    void streamChat(String model, List<Map<String, String>> messages, boolean enableThinking,
                    Integer thinkingBudget, BiConsumer<String, String> onDelta);

    /**
     * 收集流式增量，得到一次性文本结果。适合短文本分类、改写等内部轻量任务。
     */
    default String completeChat(String model, List<Map<String, String>> messages) {
        StringBuilder sb = new StringBuilder();
        streamChat(model, messages, false, null, (type, content) -> {
            if ("content".equals(type) && content != null) {
                sb.append(content);
            }
        });
        return sb.toString();
    }
}
