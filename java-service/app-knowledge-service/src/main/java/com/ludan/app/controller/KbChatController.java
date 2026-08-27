package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.entity.KbChatMessage;
import com.ludan.app.entity.KbChatSession;
import com.ludan.app.service.KbChatService;
import com.ludan.common.interf.management.annotation.Open;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.HashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 问AI / 检索 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb")
@Api(tags = "问AI/检索")
@RequiredArgsConstructor
public class KbChatController {

    private final KbChatService chatService;

    @ApiOperation("问AI（SSE流式）")
    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@RequestBody Map<String, Object> body) {
        Long kbId = body.get("kbId") != null ? Long.valueOf(body.get("kbId").toString()) : null;
        Long sessionId = body.get("sessionId") != null ? Long.valueOf(body.get("sessionId").toString()) : null;
        String userId = requireStringParam(body.get("userId"), "userId");
        String question = (String) body.get("question");
        Boolean enableThinking = body.get("enableThinking") != null
                ? Boolean.valueOf(body.get("enableThinking").toString()) : false;
        Integer thinkingBudget = body.get("thinkingBudget") != null
                ? Integer.valueOf(body.get("thinkingBudget").toString()) : null;
        Map<String, Object> retrievalOptions = body.get("options") instanceof Map
                ? new HashMap<>((Map<String, Object>) body.get("options")) : new HashMap<>();
        if (body.containsKey("graph")) {
            retrievalOptions.put("graph", Boolean.valueOf(String.valueOf(body.get("graph"))));
        }
        return chatService.chat(kbId, sessionId, userId, question, enableThinking, thinkingBudget,
                retrievalOptions);
    }

    @ApiOperation("会话列表")
    @GetMapping("/chat/sessions")
    public Result<List<KbChatSession>> sessions(@RequestParam Map<String, Object> params) {
        String userId = requireStringParam(params.get("userId"), "userId");
        return Result.succeed(chatService.getSessions(userId, params), "查询成功");
    }

    @ApiOperation("会话消息列表")
    @GetMapping("/chat/sessions/{sessionId}/messages")
    public PageResult<KbChatMessage> messages(@PathVariable Long sessionId,
                                               @RequestParam Map<String, Object> params) {
        Page<KbChatMessage> page = chatService.getMessages(sessionId, params);
        return PageResult.<KbChatMessage>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }

    @ApiOperation("删除会话")
    @DeleteMapping("/chat/sessions/{sessionId}")
    public Result<Void> deleteSession(@PathVariable Long sessionId) {
        chatService.deleteSession(sessionId);
        return Result.succeed(null, "删除成功");
    }

    @ApiOperation("消息反馈")
    @PutMapping("/chat/messages/{messageId}/feedback")
    public Result<Void> feedback(@PathVariable Long messageId, @RequestBody Map<String, Object> body) {
        String feedback = (String) body.get("feedback");
        String feedbackComment = (String) body.get("feedbackComment");
        chatService.updateMessageFeedback(messageId, feedback, feedbackComment);
        return Result.succeed(null, "反馈成功");
    }

    @ApiOperation("检索测试")
    @PostMapping("/knowledge-bases/{kbId}/retrieval-test")
    public Result<List<Map<String, Object>>> retrievalTest(@PathVariable Long kbId,
                                                      @RequestBody Map<String, Object> body) {
        try {
            String query = body.get("query") != null ? body.get("query").toString().trim() : "";
            if (query.isEmpty()) {
                return Result.failed("检索语句 query 不能为空");
            }
            Integer topK = body.get("topK") != null ? Integer.valueOf(body.get("topK").toString()) : 5;
            if (topK <= 0 || topK > 50) {
                return Result.failed("topK 取值范围为 1-50");
            }
            Map<String, Object> options = body.get("options") instanceof Map
                    ? new HashMap<>((Map<String, Object>) body.get("options")) : new HashMap<>();
            if (body.containsKey("graph")) {
                options.put("graph", Boolean.valueOf(String.valueOf(body.get("graph"))));
            }
            return Result.succeed(chatService.retrievalTest(kbId, query, topK, options), "查询成功");
        } catch (NumberFormatException e) {
            return Result.failed("topK 参数格式不正确");
        } catch (RuntimeException e) {
            log.warn("检索测试失败: kbId={}, msg={}", kbId, e.getMessage());
            return Result.failed(e.getMessage() != null ? e.getMessage() : "检索失败");
        }
    }

    @ApiOperation("多库检索测试")
    @PostMapping("/retrieval-test")
    public Result<List<Map<String, Object>>> retrievalTestMulti(@RequestBody Map<String, Object> body) {
        try {
            List<Long> kbIds = parseKbIds(body.get("kbIds"));
            if (kbIds == null || kbIds.isEmpty()) {
                return Result.failed("kbIds 不能为空");
            }
            String query = body.get("query") != null ? body.get("query").toString().trim() : "";
            if (query.isEmpty()) {
                return Result.failed("检索语句 query 不能为空");
            }
            Integer topK = body.get("topK") != null ? Integer.valueOf(body.get("topK").toString()) : 5;
            if (topK <= 0 || topK > 100) {
                return Result.failed("topK 取值范围为 1-100");
            }
            Map<String, Object> options = body.get("options") instanceof Map
                    ? new HashMap<>((Map<String, Object>) body.get("options")) : new HashMap<>();
            if (body.get("fileNodeIds") instanceof List) {
                options.put("fileNodeIds", body.get("fileNodeIds"));
            }
            if (body.containsKey("graph")) {
                options.put("graph", Boolean.valueOf(String.valueOf(body.get("graph"))));
            }
            return Result.succeed(chatService.retrievalTestMulti(kbIds, query, topK, options), "查询成功");
        } catch (NumberFormatException e) {
            return Result.failed("参数格式不正确");
        } catch (RuntimeException e) {
            log.warn("多库检索测试失败: msg={}", e.getMessage());
            return Result.failed(e.getMessage() != null ? e.getMessage() : "检索失败");
        }
    }

    private List<Long> parseKbIds(Object value) {
        if (value instanceof List) {
            return ((List<?>) value).stream()
                    .filter(v -> v != null)
                    .map(v -> Long.valueOf(v.toString().trim()))
                    .collect(Collectors.toList());
        }
        return null;
    }

    /**
     * 读取必填字符串参数，不使用默认用户兜底，避免掩盖前后端身份契约问题。
     */
    private String requireStringParam(Object value, String fieldName) {
        if (value == null || value.toString().trim().isEmpty()) {
            throw new IllegalArgumentException(fieldName + "不能为空");
        }
        return value.toString().trim();
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<Map<String, Object>> handleChatException(RuntimeException e) {
        log.warn("问AI/检索请求失败: msg={}", e.getMessage());
        String msg = e.getMessage() != null ? e.getMessage() : "请求失败";
        Map<String, Object> body = new java.util.LinkedHashMap<>();
        body.put("resp_code", "500");
        body.put("resp_msg", msg);
        body.put("data", null);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
