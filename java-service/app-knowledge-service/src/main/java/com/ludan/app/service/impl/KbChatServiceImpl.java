package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.entity.KbChatMessage;
import com.ludan.app.entity.KbChatMessageCitation;
import com.ludan.app.entity.KbChatSession;
import com.ludan.app.config.RetrievalEngineProperties;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.mapper.KbChatMessageCitationMapper;
import com.ludan.app.mapper.KbChatMessageMapper;
import com.ludan.app.mapper.KbChatSessionMapper;
import com.ludan.app.mapper.KbFileNodeMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.service.KbChatService;
import com.ludan.app.service.KbPermissionService;
import com.ludan.app.service.RetrievalEngineClient;
import com.ludan.app.service.SiliconFlowChatClient;
import com.ludan.app.service.model.RetrievalEngineHit;
import com.ludan.app.support.KbRagProfileResolver;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.collections4.MapUtils;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.math.BigDecimal;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

/**
 * 问AI/检索 Service 实现
 * <p>
 * SSE 流式问答的实际 AI 调用需对接 AI 引擎服务，此处提供骨架和模拟实现。
 *
 * @author ludan
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbChatServiceImpl implements KbChatService {

    private final KbChatSessionMapper sessionMapper;
    private final KbChatMessageMapper messageMapper;
    private final KbChatMessageCitationMapper citationMapper;
    private final KbFileNodeMapper fileNodeMapper;
    private final KbKnowledgeBaseMapper knowledgeBaseMapper;
    private final SiliconFlowChatClient siliconFlowChatClient;
    private final ObjectMapper objectMapper;
    private final RetrievalEngineClient retrievalEngineClient;
    private final RetrievalEngineProperties retrievalEngineProperties;
    private final KbPermissionService permissionService;
    private final KbRagProfileResolver ragProfileResolver;

    private final ExecutorService sseExecutor = Executors.newCachedThreadPool();

    @Override
    public SseEmitter chat(Long kbId, Long sessionId, String userId, String question,
                           Boolean enableThinking, Integer thinkingBudget,
                           Map<String, Object> retrievalOptions) {
        SseEmitter emitter = new SseEmitter(120_000L);
        boolean actualEnableThinking = Boolean.TRUE.equals(enableThinking);
        if (question == null || question.trim().isEmpty()) {
            throw new RuntimeException("问题不能为空");
        }
        String actualQuestion = question.trim();
        List<KbKnowledgeBase> scopeKbs = resolveChatScope(kbId, userId);
        if (scopeKbs.isEmpty()) {
            throw new RuntimeException(kbId == null ? "当前用户无可用知识库" : "知识库不存在或无权访问");
        }

        // 如果没有会话则创建
        if (sessionId == null) {
            KbChatSession session = new KbChatSession();
            session.setKbId(kbId);
            session.setScopeType(kbId == null ? "multi" : "single");
            session.setScopeKbIds(toKbIdJson(scopeKbs));
            session.setUserId(userId);
            session.setTitle(actualQuestion.length() > 50 ? actualQuestion.substring(0, 50) + "..." : actualQuestion);
            session.setLastMessageAt(new Date());
            sessionMapper.insert(session);
            sessionId = session.getId();
        } else {
            KbChatSession session = sessionMapper.selectById(sessionId);
            if (session == null) {
                throw new RuntimeException("会话不存在");
            }
            if (!Objects.equals(session.getUserId(), userId)) {
                throw new RuntimeException("仅会话创建人可以继续复用该会话");
            }
            session.setLastMessageAt(new Date());
            sessionMapper.updateById(session);
        }

        // 保存用户消息
        int userSeq = getNextSeqNo(sessionId);
        KbChatMessage userMsg = new KbChatMessage();
        userMsg.setSessionId(sessionId);
        userMsg.setKbId(kbId);
        userMsg.setRole("user");
        userMsg.setSeqNo(userSeq);
        userMsg.setContent(actualQuestion);
        userMsg.setStatus("completed");
        messageMapper.insert(userMsg);

        // 保存 assistant 消息占位
        int assistantSeq = userSeq + 1;
        KbChatMessage assistantMsg = new KbChatMessage();
        assistantMsg.setSessionId(sessionId);
        assistantMsg.setKbId(kbId);
        assistantMsg.setRole("assistant");
        assistantMsg.setSeqNo(assistantSeq);
        assistantMsg.setContent("");
        assistantMsg.setStatus("generating");
        assistantMsg.setParentMessageId(userMsg.getId());
        messageMapper.insert(assistantMsg);

        // 异步 SSE 推流，保持前端现有 data: JSON 协议。
        Long finalSessionId = sessionId;
        Long assistantMsgId = assistantMsg.getId();
        sseExecutor.execute(() -> {
            StringBuilder sb = new StringBuilder();
            StringBuilder reasoningSb = new StringBuilder();
            try {
                String model = resolveChatModel(kbId);
                ChatIntent intent = classifyIntent(actualQuestion, scopeKbs, model);
                sendIntent(emitter, finalSessionId, assistantMsgId, intent, scopeKbs);

                if (intent.isFileAction()) {
                    String content = buildFileActionContent(intent);
                    sb.append(content);
                    sendContent(emitter, finalSessionId, assistantMsgId, content);

                    Map<String, Object> doneData = new HashMap<>();
                    doneData.put("type", "done");
                    doneData.put("sessionId", finalSessionId);
                    doneData.put("messageId", assistantMsgId);
                    doneData.put("thinking", false);
                    doneData.put("citations", Collections.emptyList());
                    emitter.send(SseEmitter.event().data(doneData));

                    KbChatMessage msg = messageMapper.selectById(assistantMsgId);
                    if (msg != null) {
                        msg.setContent(sb.toString());
                        msg.setStatus("completed");
                        msg.setFinishedAt(new Date());
                        messageMapper.updateById(msg);
                    }
                    emitter.complete();
                    return;
                }

                boolean casualChat = "casual_chat".equals(intent.intent);
                List<RetrievalEngineHit> retrievalHits = casualChat
                        ? new ArrayList<>()
                        : retrieveForChat(scopeKbs, actualQuestion, retrievalOptions);
                List<Map<String, String>> messages = buildChatMessages(actualQuestion, retrievalHits, casualChat);
                siliconFlowChatClient.streamChat(model, messages, actualEnableThinking, thinkingBudget, (type, content) -> {
                    try {
                        if ("reasoning".equals(type)) {
                            reasoningSb.append(content);
                            sendReasoning(emitter, finalSessionId, assistantMsgId, content);
                        } else {
                            sb.append(content);
                            sendContent(emitter, finalSessionId, assistantMsgId, content);
                        }
                    } catch (Exception e) {
                        throw new RuntimeException(e);
                    }
                });
                List<Map<String, Object>> citations = buildCitationPayload(retrievalHits);
                saveCitations(assistantMsgId, finalSessionId, retrievalHits);

                // 发送结束帧
                Map<String, Object> doneData = new HashMap<>();
                doneData.put("type", "done");
                doneData.put("sessionId", finalSessionId);
                doneData.put("messageId", assistantMsgId);
                doneData.put("thinking", actualEnableThinking && reasoningSb.length() > 0);
                doneData.put("citations", citations);
                emitter.send(SseEmitter.event().data(doneData));

                // 更新 assistant 消息
                KbChatMessage msg = messageMapper.selectById(assistantMsgId);
                if (msg != null) {
                    msg.setContent(sb.toString());
                    msg.setStatus("completed");
                    msg.setFinishedAt(new Date());
                    messageMapper.updateById(msg);
                }
                emitter.complete();
            } catch (Exception e) {
                log.error("SSE推流异常", e);
                updateAssistantFailed(assistantMsgId, sb.toString(), e.getMessage());
                sendError(emitter, finalSessionId, assistantMsgId, e.getMessage());
                emitter.complete();
            }
        });

        return emitter;
    }

    @Override
    public List<KbChatSession> getSessions(String userId, Map<String, Object> params) {
        LambdaQueryWrapper<KbChatSession> query = new LambdaQueryWrapper<KbChatSession>()
                .eq(KbChatSession::getUserId, userId);
        Long kbId = getLongParam(params, "kbId");
        if (kbId != null) {
            query.eq(KbChatSession::getKbId, kbId);
        }
        return sessionMapper.selectList(query.orderByDesc(KbChatSession::getLastMessageAt));
    }

    @Override
    public Page<KbChatMessage> getMessages(Long sessionId, Map<String, Object> params) {
        Page<KbChatMessage> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 50)
        );
        Page<KbChatMessage> result = messageMapper.selectPage(page, new LambdaQueryWrapper<KbChatMessage>()
                .eq(KbChatMessage::getSessionId, sessionId)
                .orderByAsc(KbChatMessage::getSeqNo));
        fillMessageCitations(result.getRecords());
        return result;
    }

    @Override
    public void deleteSession(Long sessionId) {
        sessionMapper.deleteById(sessionId);
    }

    @Override
    public void updateMessageFeedback(Long messageId, String feedback, String feedbackComment) {
        KbChatMessage msg = messageMapper.selectById(messageId);
        if (msg == null) {
            throw new RuntimeException("消息不存在");
        }
        if (!"assistant".equals(msg.getRole())) {
            throw new RuntimeException("仅支持反馈AI回复");
        }
        msg.setFeedback(feedback);
        msg.setFeedbackComment(feedbackComment);
        messageMapper.updateById(msg);
    }

    @Override
    public List<Map<String, Object>> retrievalTest(Long kbId, String query, Integer topK,
                                                   Map<String, Object> options) {
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        if (kb == null) {
            throw new RuntimeException("知识库不存在");
        }
        if (query == null || query.trim().isEmpty()) {
            throw new RuntimeException("检索语句不能为空");
        }
        if (!retrievalEngineProperties.isEnabled()) {
            List<Map<String, Object>> disabledResults = new ArrayList<>();
            Map<String, Object> item = new HashMap<>();
            item.put("chunkId", 0L);
            item.put("content", "检索引擎已关闭（retrieval-engine.enabled=false），请在配置中开启并确保 app-rag-doc 可用");
            item.put("score", 0.0);
            item.put("retrieverType", "none");
            item.put("title", "");
            item.put("fileNodeId", null);
            item.put("metadata", null);
            item.put("raw", null);
            disabledResults.add(item);
            return disabledResults;
        }
        int tk = topK != null && topK > 0 ? topK : 5;
        List<RetrievalEngineHit> hits = retrievalEngineClient.retrieveForKnowledgeBases(
                Collections.singletonList(kbId), query, tk,
                ragProfileResolver.buildRetrieveOptions(kb, normalizeRetrievalOptions(options)));
        return buildRetrievalTestResult(hits);
    }

    @Override
    public List<Map<String, Object>> retrievalTestMulti(List<Long> kbIds, String query, Integer topK,
                                                         Map<String, Object> options) {
        if (kbIds == null || kbIds.isEmpty()) {
            throw new RuntimeException("kbIds 不能为空");
        }
        if (query == null || query.trim().isEmpty()) {
            throw new RuntimeException("检索语句不能为空");
        }
        if (!retrievalEngineProperties.isEnabled()) {
            List<Map<String, Object>> disabledResults = new ArrayList<>();
            Map<String, Object> item = new HashMap<>();
            item.put("chunkId", 0L);
            item.put("content", "检索引擎已关闭（retrieval-engine.enabled=false），请在配置中开启并确保 app-rag-doc 可用");
            item.put("score", 0.0);
            item.put("retrieverType", "none");
            item.put("title", "");
            item.put("fileNodeId", null);
            item.put("metadata", null);
            item.put("raw", null);
            disabledResults.add(item);
            return disabledResults;
        }
        // 多库检索直接使用统一的检索方法，统一使用 kb_ids 参数
        int tk = topK != null && topK > 0 ? topK : 5;
        Map<String, Object> normalizedOpts = normalizeRetrievalOptions(options);
        List<RetrievalEngineHit> hits = retrievalEngineClient.retrieveForKnowledgeBases(
                kbIds, query, tk, normalizedOpts);
        return buildRetrievalTestResult(hits);
    }

    /**
     * 将检索命中转换为前端结果 Map，含批量查询 fileNodeId → kb_file_node.original_name。
     */
    private List<Map<String, Object>> buildRetrievalTestResult(List<RetrievalEngineHit> hits) {
        // 批量收集 fileNodeId
        Set<Long> fileNodeIds = new HashSet<>();
        for (RetrievalEngineHit hit : hits) {
            Map<String, Object> meta = hit.getMetadata();
            if (meta != null) {
                Object fnId = meta.get("file_node_id");
                if (fnId != null) {
                    try {
                        fileNodeIds.add(Long.valueOf(fnId.toString()));
                    } catch (NumberFormatException ignored) {
                    }
                }
            }
        }
        // 批量查 kb_file_node.original_name
        Map<Long, KbFileNode> fileNodeMap = new HashMap<>();
        if (!fileNodeIds.isEmpty()) {
            List<KbFileNode> fileNodes = fileNodeMapper.selectBatchIds(fileNodeIds);
            if (fileNodes != null) {
                for (KbFileNode fn : fileNodes) {
                    fileNodeMap.put(fn.getId(), fn);
                }
            }
        }

        List<Map<String, Object>> results = new ArrayList<>();
        for (RetrievalEngineHit hit : hits) {
            Map<String, Object> meta = hit.getMetadata();
            Map<String, Object> item = new HashMap<>();
            item.put("chunkId", hit.getChunkId());
            item.put("content", hit.getSnippet());
            item.put("score", hit.getScore());
            item.put("retrieverType", hit.getRetrieverType());
            item.put("hitType", meta != null ? meta.get("hit_type") : null);
            item.put("title", meta != null ? meta.get("title") : null);
            item.put("fileNodeId", meta != null ? meta.get("file_node_id") : null);
            item.put("fileId", resolveFileCenterId(meta, fileNodeMap));
            item.put("fileName", resolveFileName(meta, fileNodeMap));
            item.put("raw", hit.getRawData());
            results.add(item);
        }
        return results;
    }

    /**
     * 安全解码可能含 URL 编码的文件名（引擎返回的 metadata.file_name 可能被 percent-encode）。
     */
    private String safeDecodeFileName(String name) {
        if (name == null || name.isEmpty()) return name;
        try {
            return URLDecoder.decode(name, StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            return name;
        }
    }

    private String resolveFileName(Map<String, Object> meta, Map<Long, KbFileNode> fileNodeMap) {
        if (meta == null) {
            return null;
        }
        Object fnId = meta.get("file_node_id");
        if (fnId != null) {
            try {
                KbFileNode fn = fileNodeMap.get(Long.valueOf(fnId.toString()));
                if (fn != null && fn.getOriginalName() != null) {
                    return fn.getOriginalName();
                }
            } catch (NumberFormatException ignored) {
            }
        }
        Object fnMeta = meta.get("file_name");
        return fnMeta != null ? safeDecodeFileName(fnMeta.toString()) : null;
    }

    /**
     * 根据 metadata.file_node_id 从 kb_file_node 批量查询结果中解析文件中心 file_id。
     */
    private String resolveFileCenterId(Map<String, Object> meta, Map<Long, KbFileNode> fileNodeMap) {
        if (meta == null) {
            return null;
        }
        Object fnId = meta.get("file_node_id");
        if (fnId == null) {
            return null;
        }
        try {
            KbFileNode fn = fileNodeMap.get(Long.valueOf(fnId.toString()));
            return fn != null ? fn.getFileId() : null;
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private Map<String, Object> normalizeRetrievalOptions(Map<String, Object> options) {
        if (options == null || options.isEmpty()) {
            return null;
        }
        Map<String, Object> normalized = new HashMap<>();
        for (Map.Entry<String, Object> entry : options.entrySet()) {
            Object value = entry.getValue();
            if (value == null) {
                continue;
            }
            if (value instanceof String && ((String) value).trim().isEmpty()) {
                continue;
            }
            if (value instanceof Collection && ((Collection<?>) value).isEmpty()) {
                continue;
            }
            normalized.put(entry.getKey(), value);
        }
        return normalized;
    }

    /**
     * 获取会话中下一个消息序号
     */
    private int getNextSeqNo(Long sessionId) {
        Long count = messageMapper.selectCount(new LambdaQueryWrapper<KbChatMessage>()
                .eq(KbChatMessage::getSessionId, sessionId));
        return count != null ? count.intValue() + 1 : 1;
    }

    /**
     * 根据知识库 model_profile 选择聊天模型，未配置时使用客户端默认模型。
     */
    private String resolveChatModel(Long kbId) {
        if (kbId == null) {
            return null;
        }
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        if (kb == null || isBlank(kb.getModelProfile())) {
            return null;
        }
        try {
            JsonNode root = objectMapper.readTree(kb.getModelProfile());
            JsonNode model = root.path("chat").path("model");
            return model.isMissingNode() || model.isNull() || isBlank(model.asText()) ? null : model.asText();
        } catch (Exception e) {
            log.warn("知识库模型配置解析失败，使用默认模型: kbId={}", kbId, e);
            return null;
        }
    }

    /**
     * 构造大模型消息，后续接入检索结果时可在 system 内容中注入上下文。
     */
    private List<Map<String, String>> buildChatMessages(String question, List<RetrievalEngineHit> hits, boolean casualChat) {
        List<Map<String, String>> messages = new ArrayList<>();
        Map<String, String> system = new HashMap<>(2);
        system.put("role", "system");
        system.put("content", buildSystemPrompt(hits, casualChat));
        messages.add(system);
        Map<String, String> user = new HashMap<>(2);
        user.put("role", "user");
        user.put("content", question);
        messages.add(user);
        return messages;
    }

    private String buildSystemPrompt(List<RetrievalEngineHit> hits, boolean casualChat) {
        StringBuilder prompt = new StringBuilder();
        if (casualChat) {
            prompt.append("你是企业知识库问答助手。当前用户在进行日常寒暄或轻量交流。");
            prompt.append("请自然、简短、礼貌地回应，不要检索知识库，不要输出引用来源，不要编造业务结论。");
            return prompt.toString();
        }
        prompt.append("你是企业知识库问答助手，请只基于给定知识库召回内容回答。");
        prompt.append("如果召回内容不足以回答，请明确说明未在知识库中找到可靠依据。");
        prompt.append("回答使用中文，结论简洁。");
        prompt.append("不要单独输出“依据”段落；所有来源只在正文中用 [1]、[2] 这类编号标注，");
        prompt.append("详细来源交给页面下方的引用来源区展示。");
        prompt.append("请使用规范 Markdown：段落之间保留空行；如果需要列点，使用数字列表（如“1. ...”），");
        prompt.append("不要把加粗标记、标题和列表黏在同一行。");
        prompt.append("如果召回项包含 graph_path，可用它解释主体、关系和关联对象；图关系只作补充，最终结论仍须有对应 Chunk 原文证据。");
        prompt.append("如果召回项是社区报告，只用于回答跨文档全局问题；具体事实仍应优先引用原文 Chunk。");
        if (hits == null || hits.isEmpty()) {
            prompt.append("\n\n本次未召回到知识库片段。");
            return prompt.toString();
        }
        prompt.append("\n\n知识库召回内容：\n");
        int totalBudget = Math.max(2000, retrievalEngineProperties.getContextMaxChars());
        double textRatio = Math.max(0D, retrievalEngineProperties.getTextContextRatio());
        double graphRatio = Math.max(0D, retrievalEngineProperties.getGraphContextRatio());
        double communityRatio = Math.max(0D, retrievalEngineProperties.getCommunityContextRatio());
        double ratioTotal = textRatio + graphRatio + communityRatio;
        if (ratioTotal <= 0D) {
            textRatio = 0.50D;
            graphRatio = 0.35D;
            communityRatio = 0.15D;
            ratioTotal = 1D;
        }
        int textRemaining = (int) Math.floor(totalBudget * textRatio / ratioTotal);
        int graphRemaining = (int) Math.floor(totalBudget * graphRatio / ratioTotal);
        int communityRemaining = Math.max(0, totalBudget - textRemaining - graphRemaining);
        int i = 1;
        for (RetrievalEngineHit hit : hits) {
            if (i > 12) {
                break;
            }
            Map<String, Object> meta = hit.getMetadata();
            boolean communityHit = meta != null && (
                    "community_report".equals(String.valueOf(meta.get("type")))
                            || "community_report".equals(String.valueOf(meta.get("hit_type")))
                            || "graph_global".equals(String.valueOf(meta.get("route")))
            );
            String graphText = "";
            if (meta != null && meta.get("graph_path") != null && graphRemaining > 0) {
                graphText = truncate(toJsonValueString(meta.get("graph_path")), Math.min(600, graphRemaining));
            }
            String snippet = hit.getSnippet() == null ? "" : hit.getSnippet();
            String evidenceText;
            if (communityHit) {
                evidenceText = truncate(snippet, Math.min(2000, communityRemaining));
            } else {
                evidenceText = truncate(snippet, Math.min(1200, textRemaining));
            }
            if (graphText.isEmpty() && evidenceText.isEmpty()) {
                continue;
            }
            StringBuilder item = new StringBuilder();
            item.append("[").append(i).append("] ");
            if (meta != null) {
                Object kb = meta.get("kb_id");
                Object file = meta.get("file_node_id");
                Object title = meta.get("title");
                if (kb != null) {
                    item.append("kb_id=").append(kb).append(" ");
                }
                if (file != null) {
                    item.append("file_node_id=").append(file).append(" ");
                }
                if (title != null) {
                    item.append("title=").append(title).append(" ");
                }
            }
            if (!graphText.isEmpty()) {
                item.append("\n图关系=").append(graphText).append("\n");
                graphRemaining -= graphText.length();
            }
            item.append("score=").append(hit.getScore() == null ? "" : hit.getScore()).append("\n");
            item.append(evidenceText).append("\n");
            if (communityHit) {
                communityRemaining -= evidenceText.length();
            } else {
                textRemaining -= evidenceText.length();
            }
            prompt.append(item);
            i++;
        }
        return prompt.toString();
    }

    private boolean isCasualChat(String question) {
        if (question == null) {
            return true;
        }
        String text = question.trim();
        if (text.isEmpty()) {
            return true;
        }
        String lower = text.toLowerCase(Locale.ROOT);
        String normalized = text.replaceAll("\\s+", "");
        if (normalized.length() <= 6) {
            String[] casualKeywords = {"你好", "您好", "嗨", "在吗", "在么", "在不", "谢谢", "早上好", "下午好", "晚上好", "hello", "hi"};
            for (String keyword : casualKeywords) {
                if (lower.contains(keyword) || normalized.contains(keyword)) {
                    return true;
                }
            }
        }
        return normalized.matches("(?i)^(你好|您好|嗨|在吗|谢谢|hello|hi|hey|good\\s*(morning|afternoon|evening))$");
    }

    private ChatIntent classifyIntent(String question, List<KbKnowledgeBase> scopeKbs, String model) {
        String text = question == null ? "" : question.trim();
        String normalized = text.replaceAll("\\s+", "");
        String lower = text.toLowerCase(Locale.ROOT);
        if (isCasualChat(text)) {
            return ChatIntent.of("casual_chat", text, 0.98, "命中寒暄问候");
        }
        if (containsAny(normalized, "最近更新的文档", "最近更新文件", "最新更新文档", "最新上传文档",
                "最近上传文档", "最近文档", "最新文档", "更新的文档", "新上传的文件", "最近更新")) {
            ChatIntent intent = ChatIntent.of("file_recent", "", 0.92, "用户想查看最近更新或上传的文档");
            intent.files = listRecentFilesForChat(scopeKbs, resolveSafePageSize(text));
            return intent;
        }
        if (containsAny(normalized, "搜文件", "搜索文件", "找文件", "查文件", "文件列表", "有哪些文件",
                "相关文件", "关联文件", "文档列表", "查文档", "找文档", "搜索文档")
                || lower.startsWith("file_search")) {
            String query = normalizeFileSearchQuery(text);
            ChatIntent intent = ChatIntent.of("file_search", query, 0.86, "用户想定位文件而不是直接问答");
            intent.files = searchFilesForChat(scopeKbs, query, 8);
            return intent;
        }
        ChatIntent modelIntent = classifyIntentByModel(text, scopeKbs, model);
        if (modelIntent != null) {
            if ("file_recent".equals(modelIntent.intent)) {
                modelIntent.files = listRecentFilesForChat(scopeKbs, resolveSafePageSize(text));
            } else if ("file_search".equals(modelIntent.intent)) {
                modelIntent.files = searchFilesForChat(scopeKbs, modelIntent.query, 8);
            }
            return modelIntent;
        }
        return ChatIntent.of("knowledge_qa", text, 0.72, "默认按知识库问答处理");
    }

    private ChatIntent classifyIntentByModel(String question, List<KbKnowledgeBase> scopeKbs, String model) {
        if (isBlank(question)) {
            return null;
        }
        try {
            List<Map<String, String>> messages = new ArrayList<>();
            Map<String, String> system = new HashMap<>();
            system.put("role", "system");
            system.put("content", "你是企业知识库聊天入口的意图分类器。"
                    + "只输出JSON，不要输出Markdown。intent只能是casual_chat、knowledge_qa、file_search、file_recent。"
                    + "casual_chat=寒暄感谢等无需知识库；knowledge_qa=询问制度、政策、字段、内容答案；"
                    + "file_search=想找某个文件/文档/材料；file_recent=想看最近更新、最近上传、最新文档。"
                    + "字段：intent、query、confidence、reason。query用于文件搜索，无法提取则为空字符串。");
            messages.add(system);
            Map<String, String> user = new HashMap<>();
            user.put("role", "user");
            user.put("content", "用户问题：" + question + "\n可用知识库数量：" + (scopeKbs == null ? 0 : scopeKbs.size()));
            messages.add(user);
            String raw = siliconFlowChatClient.completeChat(model, messages);
            JsonNode node = objectMapper.readTree(extractJsonObject(raw));
            String intent = node.path("intent").asText("knowledge_qa");
            if (!Arrays.asList("casual_chat", "knowledge_qa", "file_search", "file_recent").contains(intent)) {
                return null;
            }
            String query = node.path("query").asText("");
            double confidence = node.path("confidence").isNumber() ? node.path("confidence").asDouble() : 0.6D;
            if (confidence < 0.55D) {
                return null;
            }
            String reason = node.path("reason").asText("AI意图识别");
            return ChatIntent.of(intent, isBlank(query) ? question : query, confidence, reason);
        } catch (Exception e) {
            log.warn("AI意图识别失败，回退默认知识问答: {}", e.getMessage());
            return null;
        }
    }

    private String extractJsonObject(String raw) {
        if (raw == null) {
            return "{}";
        }
        String text = raw.trim();
        int start = text.indexOf('{');
        int end = text.lastIndexOf('}');
        if (start >= 0 && end > start) {
            return text.substring(start, end + 1);
        }
        return text;
    }

    private boolean containsAny(String text, String... keywords) {
        if (text == null) {
            return false;
        }
        for (String keyword : keywords) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private String normalizeFileSearchQuery(String question) {
        if (question == null) {
            return "";
        }
        return question
                .replaceAll("(?i)file_search", "")
                .replaceAll("(帮我|请|一下|看看|查看|搜索|搜|查找|查|找|相关|关联|文件|文档|有哪些|列表)", " ")
                .replaceAll("\\s+", " ")
                .trim();
    }

    private int resolveSafePageSize(String question) {
        if (question != null && question.contains("全部")) {
            return 12;
        }
        return 8;
    }

    private String buildFileActionContent(ChatIntent intent) {
        if ("file_recent".equals(intent.intent)) {
            return intent.files == null || intent.files.isEmpty()
                    ? "当前知识范围内暂未找到最近更新的文档。"
                    : "已为你整理最近更新的文档，点击文件卡片可以预览。";
        }
        if ("file_search".equals(intent.intent)) {
            return intent.files == null || intent.files.isEmpty()
                    ? "我会按文件搜索处理这个请求，你可以点击下方按钮进入搜文件页继续筛选。"
                    : "已按文件搜索理解你的请求，下方是匹配到的文件。";
        }
        return "";
    }

    private void sendIntent(SseEmitter emitter, Long sessionId, Long messageId, ChatIntent intent,
                            List<KbKnowledgeBase> scopeKbs) throws Exception {
        Map<String, Object> data = new HashMap<>();
        data.put("type", "intent");
        data.put("sessionId", sessionId);
        data.put("messageId", messageId);
        data.put("intent", intent.intent);
        data.put("query", intent.query);
        data.put("confidence", intent.confidence);
        data.put("reason", intent.reason);
        data.put("files", intent.files == null ? Collections.emptyList() : intent.files);
        data.put("scopeKbIds", scopeKbs == null ? Collections.emptyList() :
                scopeKbs.stream().map(KbKnowledgeBase::getId).collect(Collectors.toList()));
        emitter.send(SseEmitter.event().data(data));
    }

    private List<Map<String, Object>> listRecentFilesForChat(List<KbKnowledgeBase> scopeKbs, int pageSize) {
        LambdaQueryWrapper<KbFileNode> query = baseFileQuery(scopeKbs)
                .orderByDesc(KbFileNode::getUpdateTime)
                .orderByDesc(KbFileNode::getCreateTime)
                .last("LIMIT " + Math.max(1, Math.min(pageSize, 12)));
        return toChatFileItems(fileNodeMapper.selectList(query));
    }

    private List<Map<String, Object>> searchFilesForChat(List<KbKnowledgeBase> scopeKbs, String queryText, int pageSize) {
        LambdaQueryWrapper<KbFileNode> query = baseFileQuery(scopeKbs);
        if (!isBlank(queryText)) {
            query.and(wrapper -> wrapper
                    .like(KbFileNode::getName, queryText)
                    .or()
                    .like(KbFileNode::getOriginalName, queryText));
        }
        query.orderByDesc(KbFileNode::getUpdateTime)
                .orderByDesc(KbFileNode::getCreateTime)
                .last("LIMIT " + Math.max(1, Math.min(pageSize, 12)));
        return toChatFileItems(fileNodeMapper.selectList(query));
    }

    private LambdaQueryWrapper<KbFileNode> baseFileQuery(List<KbKnowledgeBase> scopeKbs) {
        LambdaQueryWrapper<KbFileNode> query = new LambdaQueryWrapper<KbFileNode>()
                .eq(KbFileNode::getNodeType, "file");
        List<Long> kbIds = scopeKbs == null ? Collections.emptyList() :
                scopeKbs.stream().map(KbKnowledgeBase::getId).filter(Objects::nonNull).collect(Collectors.toList());
        if (kbIds.isEmpty()) {
            query.eq(KbFileNode::getKbId, -1L);
        } else if (kbIds.size() == 1) {
            query.eq(KbFileNode::getKbId, kbIds.get(0));
        } else {
            query.in(KbFileNode::getKbId, kbIds);
        }
        return query;
    }

    private List<Map<String, Object>> toChatFileItems(List<KbFileNode> nodes) {
        if (nodes == null || nodes.isEmpty()) {
            return Collections.emptyList();
        }
        Set<Long> kbIds = nodes.stream().map(KbFileNode::getKbId).filter(Objects::nonNull).collect(Collectors.toSet());
        Map<Long, String> kbNames = new HashMap<>();
        if (!kbIds.isEmpty()) {
            for (KbKnowledgeBase kb : knowledgeBaseMapper.selectBatchIds(kbIds)) {
                kbNames.put(kb.getId(), kb.getName());
            }
        }
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd HH:mm");
        List<Map<String, Object>> files = new ArrayList<>();
        for (KbFileNode node : nodes) {
            Map<String, Object> item = new HashMap<>();
            item.put("id", node.getId());
            item.put("fileNodeId", node.getId());
            item.put("fileId", node.getFileId());
            item.put("kbId", node.getKbId());
            item.put("kbName", kbNames.get(node.getKbId()));
            item.put("name", firstNonBlank(node.getOriginalName(), node.getName()));
            item.put("title", firstNonBlank(node.getOriginalName(), node.getName()));
            item.put("fileType", node.getFileExt());
            item.put("size", formatSize(node.getFileSize()));
            item.put("updateTime", node.getUpdateTime() == null ? "" : sdf.format(node.getUpdateTime()));
            files.add(item);
        }
        return files;
    }

    private String formatSize(Long bytes) {
        if (bytes == null || bytes <= 0) {
            return "";
        }
        double value = bytes;
        String[] units = {"B", "KB", "MB", "GB"};
        int unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value = value / 1024;
            unitIndex++;
        }
        return String.format(Locale.ROOT, unitIndex == 0 ? "%.0f%s" : "%.1f%s", value, units[unitIndex]);
    }

    private List<RetrievalEngineHit> retrieveForChat(List<KbKnowledgeBase> scopeKbs, String question,
                                                      Map<String, Object> retrievalOptions) {
        if (!retrievalEngineProperties.isEnabled() || scopeKbs == null || scopeKbs.isEmpty()) {
            return new ArrayList<>();
        }
        int perKbTopK = Math.max(1, Math.min(retrievalEngineProperties.getDefaultTopK(), 8));
        List<RetrievalEngineHit> hits;

        if (scopeKbs.size() == 1) {
            // 单库路径
            KbKnowledgeBase kb = scopeKbs.get(0);
            hits = retrievalEngineClient.retrieveForKnowledgeBases(
                    Collections.singletonList(kb.getId()), question, perKbTopK,
                    ragProfileResolver.buildRetrieveOptions(kb, normalizeRetrievalOptions(retrievalOptions)));
            for (RetrievalEngineHit hit : hits) {
                normalizeRetrievedHit(hit, kb.getId());
            }
        } else {
            // 多库路径：单次 HTTP
            List<Long> kbIds = scopeKbs.stream().map(KbKnowledgeBase::getId).collect(Collectors.toList());
            int totalTopK = Math.min(perKbTopK * kbIds.size(), 200);
            Map<String, Object> options = ragProfileResolver.buildRetrieveOptions(
                    scopeKbs.get(0), normalizeRetrievalOptions(retrievalOptions));
            hits = retrievalEngineClient.retrieveForKnowledgeBases(
                    kbIds, question, totalTopK, options);
            for (RetrievalEngineHit hit : hits) {
                normalizeRetrievedHit(hit, null);
            }
        }

        hits.sort(Comparator.comparing(RetrievalEngineHit::getScore, Comparator.nullsLast(Comparator.reverseOrder())));
        if (hits.size() > 12) {
            return new ArrayList<>(hits.subList(0, 12));
        }
        return hits;
    }

    private void normalizeRetrievedHit(RetrievalEngineHit hit, Long kbId) {
        if (hit == null) {
            return;
        }
        Map<String, Object> metadata = hit.getMetadata();
        if (metadata == null) {
            metadata = new HashMap<>();
            hit.setMetadata(metadata);
        }
        metadata.putIfAbsent("kb_id", kbId);
        if (hit.getChunkId() == null) {
            hit.setChunkId(getLongFromMetadata(metadata, "source_chunk_id"));
        }
    }

    private List<Map<String, Object>> buildCitationPayload(List<RetrievalEngineHit> hits) {
        List<Map<String, Object>> citations = new ArrayList<>();
        if (hits == null) {
            return citations;
        }
        int i = 1;
        for (RetrievalEngineHit hit : hits) {
            Map<String, Object> item = new HashMap<>();
            item.put("index", i++);
            item.put("chunkId", hit.getChunkId());
            item.put("score", hit.getScore());
            item.put("content", truncate(hit.getSnippet(), 300));
            Map<String, Object> metadata = enrichCitationMetadata(hit.getMetadata());
            item.put("metadata", metadata);
            item.put("graphPath", metadata.get("graph_path"));
            item.put("hitRoutes", metadata.get("route_names"));
            citations.add(item);
        }
        return citations;
    }

    private Map<String, Object> enrichCitationMetadata(Map<String, Object> metadata) {
        Map<String, Object> enriched = metadata == null ? new HashMap<>() : new HashMap<>(metadata);
        Long fileNodeId = getLongFromMetadata(enriched, "file_node_id");
        if (fileNodeId == null) {
            return enriched;
        }
        KbFileNode fileNode = fileNodeMapper.selectById(fileNodeId);
        if (fileNode == null) {
            return enriched;
        }
        enriched.put("source_file_id", fileNode.getFileId());
        enriched.put("file_node_name", fileNode.getName());
        enriched.put("original_name", fileNode.getOriginalName());
        if (isBlank(asString(enriched.get("file_name")))) {
            enriched.put("file_name", firstNonBlank(fileNode.getOriginalName(), fileNode.getName()));
        }
        return enriched;
    }

    private void saveCitations(Long messageId, Long sessionId, List<RetrievalEngineHit> hits) {
        if (hits == null || hits.isEmpty()) {
            return;
        }
        int rankNo = 1;
        for (RetrievalEngineHit hit : hits) {
            Long hitKbId = getLongFromMetadata(hit.getMetadata(), "kb_id");
            Long bizId = resolveCitationBizId(hit);
            if (hitKbId == null || bizId == null) {
                log.warn("跳过无法落库的问AI引用: messageId={}, rankNo={}, kbId={}, chunkId={}, metadata={}",
                        messageId, rankNo, hitKbId, hit.getChunkId(), hit.getMetadata());
                rankNo++;
                continue;
            }
            KbChatMessageCitation citation = new KbChatMessageCitation();
            citation.setMessageId(messageId);
            citation.setSessionId(sessionId);
            citation.setKbId(hitKbId);
            citation.setBizType("chunk");
            citation.setBizId(bizId);
            citation.setFileNodeId(getLongFromMetadata(hit.getMetadata(), "file_node_id"));
            citation.setRankNo(rankNo);
            citation.setScore(hit.getScore() == null ? null : BigDecimal.valueOf(hit.getScore()));
            citation.setRetrieverType(truncate(hit.getRetrieverType(), 16));
            citation.setIsCited(1);
            citation.setCiteIndex(rankNo);
            citation.setSnippet(truncate(hit.getSnippet(), 1000));
            citation.setPageNum(firstNonNullInteger(
                    getIntegerFromMetadata(hit.getMetadata(), "page_no"),
                    getIntegerFromMetadata(hit.getMetadata(), "page_num")
            ));
            citation.setMetadataJson(toJsonString(enrichCitationMetadata(hit.getMetadata())));
            citationMapper.insert(citation);
            rankNo++;
        }
    }

    private Long resolveCitationBizId(RetrievalEngineHit hit) {
        if (hit == null) {
            return null;
        }
        if (hit.getChunkId() != null) {
            return hit.getChunkId();
        }
        return getLongFromMetadata(hit.getMetadata(), "source_chunk_id");
    }

    private void fillMessageCitations(List<KbChatMessage> messages) {
        if (messages == null || messages.isEmpty()) {
            return;
        }
        List<Long> assistantIds = messages.stream()
                .filter(item -> "assistant".equals(item.getRole()))
                .map(KbChatMessage::getId)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        if (assistantIds.isEmpty()) {
            return;
        }
        List<KbChatMessageCitation> citations = citationMapper.selectList(new LambdaQueryWrapper<KbChatMessageCitation>()
                .in(KbChatMessageCitation::getMessageId, assistantIds)
                .orderByAsc(KbChatMessageCitation::getRankNo));
        Map<Long, List<Map<String, Object>>> citationMap = new HashMap<>();
        for (KbChatMessageCitation citation : citations) {
            citationMap.computeIfAbsent(citation.getMessageId(), key -> new ArrayList<>()).add(toCitationPayload(citation));
        }
        for (KbChatMessage message : messages) {
            message.setCitations(citationMap.getOrDefault(message.getId(), Collections.emptyList()));
        }
    }

    private Map<String, Object> toCitationPayload(KbChatMessageCitation citation) {
        Map<String, Object> item = new HashMap<>();
        item.put("index", citation.getRankNo());
        item.put("chunkId", citation.getBizId());
        item.put("score", citation.getScore());
        item.put("content", citation.getSnippet());
        Map<String, Object> metadata = readMetadataMap(citation.getMetadataJson());
        if (metadata.isEmpty()) {
            metadata = new HashMap<>();
        }
        metadata.put("kb_id", citation.getKbId());
        metadata.put("file_node_id", citation.getFileNodeId());
        metadata.put("page_no", citation.getPageNum());
        metadata.put("page_num", citation.getPageNum());
        if (citation.getFileNodeId() != null && !metadata.containsKey("source_file_id")) {
            KbFileNode fileNode = fileNodeMapper.selectById(citation.getFileNodeId());
            if (fileNode != null) {
                metadata.put("source_file_id", fileNode.getFileId());
                metadata.put("file_node_name", fileNode.getName());
                metadata.put("original_name", fileNode.getOriginalName());
                metadata.put("file_name", firstNonBlank(fileNode.getOriginalName(), fileNode.getName()));
            }
        }
        item.put("metadata", metadata);
        return item;
    }

    private String toJsonString(Map<String, Object> metadata) {
        if (metadata == null || metadata.isEmpty()) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(metadata);
        } catch (Exception e) {
            log.warn("引用元数据序列化失败", e);
            return null;
        }
    }

    private String toJsonValueString(Object value) {
        if (value == null) {
            return "";
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            log.warn("图关系序列化失败", e);
            return "";
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readMetadataMap(String metadataJson) {
        if (metadataJson == null || metadataJson.trim().isEmpty()) {
            return Collections.emptyMap();
        }
        try {
            return objectMapper.readValue(metadataJson, Map.class);
        } catch (Exception e) {
            log.warn("引用元数据反序列化失败", e);
            return Collections.emptyMap();
        }
    }

    private Long getLongFromMetadata(Map<String, Object> metadata, String key) {
        if (metadata == null || metadata.get(key) == null) {
            return null;
        }
        try {
            return Long.valueOf(metadata.get(key).toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Integer getIntegerFromMetadata(Map<String, Object> metadata, String key) {
        if (metadata == null || metadata.get(key) == null) {
            return null;
        }
        try {
            return Integer.valueOf(metadata.get(key).toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Integer firstNonNullInteger(Integer... values) {
        for (Integer value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private String asString(Object value) {
        return value == null ? null : value.toString();
    }

    private List<KbKnowledgeBase> resolveChatScope(Long kbId, String userId) {
        if (kbId == null) {
            // 多库路径：委托 permissionService 查询所有可访问库
            return permissionService.resolveAccessibleKbs(userId);
        }
        // 单库路径：只查单个库并校验权限
        KbKnowledgeBase kb = knowledgeBaseMapper.selectById(kbId);
        if (kb == null || !"active".equals(kb.getStatus())) {
            return Collections.emptyList();
        }
        if (!permissionService.canUseKb(kb, userId)) {
            return Collections.emptyList();
        }
        return Collections.singletonList(kb);
    }

    private String toKbIdJson(List<KbKnowledgeBase> kbs) {
        try {
            List<Long> ids = new ArrayList<>();
            for (KbKnowledgeBase kb : kbs) {
                ids.add(kb.getId());
            }
            return objectMapper.writeValueAsString(ids);
        } catch (Exception e) {
            return "[]";
        }
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private void sendContent(SseEmitter emitter, Long sessionId, Long messageId, String content) throws Exception {
        Map<String, Object> data = new HashMap<>();
        data.put("sessionId", sessionId);
        data.put("messageId", messageId);
        data.put("content", content);
        data.put("type", "content");
        emitter.send(SseEmitter.event().data(data));
    }

    private void sendReasoning(SseEmitter emitter, Long sessionId, Long messageId, String content) throws Exception {
        Map<String, Object> data = new HashMap<>();
        data.put("sessionId", sessionId);
        data.put("messageId", messageId);
        data.put("content", content);
        data.put("type", "reasoning");
        emitter.send(SseEmitter.event().data(data));
    }

    private void sendError(SseEmitter emitter, Long sessionId, Long messageId, String errorMsg) {
        try {
            Map<String, Object> data = new HashMap<>();
            data.put("sessionId", sessionId);
            data.put("messageId", messageId);
            data.put("content", errorMsg);
            data.put("type", "error");
            emitter.send(SseEmitter.event().data(data));
        } catch (Exception sendException) {
            log.warn("发送SSE错误帧失败", sendException);
        }
    }

    private void updateAssistantFailed(Long assistantMsgId, String partialContent, String errorMsg) {
        KbChatMessage msg = messageMapper.selectById(assistantMsgId);
        if (msg != null) {
            msg.setContent(partialContent);
            msg.setStatus("failed");
            msg.setErrorMsg(errorMsg);
            msg.setFinishedAt(new Date());
            messageMapper.updateById(msg);
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private Long getLongParam(Map<String, Object> params, String key) {
        if (params == null || params.get(key) == null || params.get(key).toString().trim().isEmpty()) {
            return null;
        }
        return Long.valueOf(params.get(key).toString());
    }

    private static class ChatIntent {
        private String intent;
        private String query;
        private Double confidence;
        private String reason;
        private List<Map<String, Object>> files = Collections.emptyList();

        private static ChatIntent of(String intent, String query, Double confidence, String reason) {
            ChatIntent value = new ChatIntent();
            value.intent = intent;
            value.query = query;
            value.confidence = confidence;
            value.reason = reason;
            return value;
        }

        private boolean isFileAction() {
            return "file_search".equals(intent) || "file_recent".equals(intent);
        }
    }
}
