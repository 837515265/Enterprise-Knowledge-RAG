package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.ludan.app.entity.KbChatMessage;
import com.ludan.app.entity.KbChatSession;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

/**
 * 问AI/检索 Service
 *
 * @author ludan
 */
public interface KbChatService {

    /**
     * 创建或复用会话并发起 SSE 流式问答
     */
    SseEmitter chat(Long kbId, Long sessionId, String userId, String question,
                    Boolean enableThinking, Integer thinkingBudget,
                    Map<String, Object> retrievalOptions);

    /**
     * 获取会话列表
     */
    List<KbChatSession> getSessions(String userId, Map<String, Object> params);

    /**
     * 获取会话消息列表
     */
    Page<KbChatMessage> getMessages(Long sessionId, Map<String, Object> params);

    /**
     * 删除会话
     */
    void deleteSession(Long sessionId);

    /**
     * 更新助手消息反馈
     */
    void updateMessageFeedback(Long messageId, String feedback, String feedbackComment);

    /**
     * 检索测试（不走AI，仅返回召回结果）
     */
    List<Map<String, Object>> retrievalTest(Long kbId, String query, Integer topK,
                                            Map<String, Object> options);

    /**
     * 多库检索测试（不走AI，仅返回召回结果）
     */
    List<Map<String, Object>> retrievalTestMulti(List<Long> kbIds, String query, Integer topK,
                                                  Map<String, Object> options);
}
