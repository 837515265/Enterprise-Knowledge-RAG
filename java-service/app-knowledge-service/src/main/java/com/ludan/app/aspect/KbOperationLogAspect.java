package com.ludan.app.aspect;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ludan.app.service.KbOperationLogService;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.HandlerMapping;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * 知识库操作日志切面。
 *
 * <p>复用 Controller 已有的 {@link ApiOperation} 描述，在写操作成功返回后统一落库，
 * 避免在业务代码里散落日志记录逻辑。</p>
 */
@Slf4j
@Aspect
@Component
@RequiredArgsConstructor
public class KbOperationLogAspect {

    private static final String KB_API_PREFIX = "/api/v1/kb";
    private static final String USER_ID_HEADER = "x-userid-header";

    private final KbOperationLogService operationLogService;
    private final ObjectMapper objectMapper;

    /**
     * Controller 写操作成功后记录操作日志。
     */
    @AfterReturning(pointcut = "@annotation(apiOperation)", returning = "result")
    public void afterSuccess(JoinPoint joinPoint, ApiOperation apiOperation, Object result) {
        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes == null) {
            return;
        }

        HttpServletRequest request = attributes.getRequest();
        String method = request.getMethod();
        String uri = request.getRequestURI();
        if (!shouldRecord(method, uri)) {
            return;
        }

        try {
            Map<String, String> pathVars = getPathVariables(request);
            Long kbId = getLong(pathVars.get("kbId"));
            OperationTarget target = resolveTarget(method, uri, pathVars);
            String summary = apiOperation.value();

            operationLogService.log(
                    kbId,
                    resolveOperatorId(request),
                    target.action,
                    target.objectType,
                    target.objectId,
                    summary,
                    buildDetailJson(method, uri, joinPoint.getArgs(), result)
            );
        } catch (Exception e) {
            // 操作日志不能影响主流程，异常只记录应用日志。
            log.warn("记录知识库操作日志失败: method={}, uri={}", method, uri, e);
        }
    }

    private boolean shouldRecord(String method, String uri) {
        return uri != null
                && uri.contains(KB_API_PREFIX)
                && !"GET".equalsIgnoreCase(method)
                && !uri.contains("/operation-logs")
                && !uri.contains("/chat/")
                && !uri.contains("/audit/");
    }

    private Map<String, String> getPathVariables(HttpServletRequest request) {
        Object attr = request.getAttribute(HandlerMapping.URI_TEMPLATE_VARIABLES_ATTRIBUTE);
        if (attr instanceof Map) {
            Map<String, String> result = new HashMap<>();
            ((Map<?, ?>) attr).forEach((key, value) -> result.put(String.valueOf(key), String.valueOf(value)));
            return result;
        }
        return new HashMap<>();
    }

    private OperationTarget resolveTarget(String method, String uri, Map<String, String> pathVars) {
        String actionVerb = resolveActionVerb(method);
        String objectType = "kb";
        String objectId = pathVars.get("kbId");

        if (uri.contains("/audit/")) {
            objectType = uri.contains("/files/") ? "file" : "qa";
            objectId = firstNonBlank(pathVars.get("fileId"), pathVars.get("qaId"));
            actionVerb = "audit";
        } else if (uri.contains("/files/") || uri.endsWith("/files") || uri.endsWith("/files/folder")) {
            objectType = "file";
            objectId = firstNonBlank(pathVars.get("fileId"), pathVars.get("kbId"));
        } else if (uri.contains("/chunks/")) {
            objectType = "chunk";
            objectId = pathVars.get("chunkId");
        } else if (uri.contains("/qa-pairs/") || uri.endsWith("/qa-pairs") || uri.contains("/qa-pairs/import")) {
            objectType = "qa";
            objectId = firstNonBlank(pathVars.get("qaId"), pathVars.get("kbId"));
        } else if (uri.contains("/members/") || uri.endsWith("/members")) {
            objectType = "member";
            objectId = firstNonBlank(pathVars.get("ruleId"), pathVars.get("kbId"));
        } else if (uri.contains("/tags/") || uri.endsWith("/tags")) {
            objectType = "tag";
            objectId = pathVars.get("tagId");
        }

        return new OperationTarget(objectType + "." + actionVerb, objectType, objectId);
    }

    private String resolveActionVerb(String method) {
        switch (method.toUpperCase(Locale.ROOT)) {
            case "POST":
                return "create";
            case "PUT":
            case "PATCH":
                return "update";
            case "DELETE":
                return "delete";
            default:
                return method.toLowerCase(Locale.ROOT);
        }
    }

    private Long resolveOperatorId(HttpServletRequest request) {
        Long operatorId = getLong(request.getHeader(USER_ID_HEADER));
        return operatorId == null ? 0L : operatorId;
    }

    private String buildDetailJson(String method, String uri, Object[] args, Object result) {
        Map<String, Object> detail = new HashMap<>();
        detail.put("method", method);
        detail.put("uri", uri);
        detail.put("args", filterArgs(args));
        detail.put("result", result);
        try {
            return objectMapper.writeValueAsString(detail);
        } catch (Exception e) {
            return "{\"method\":\"" + method + "\",\"uri\":\"" + uri + "\"}";
        }
    }

    private Object[] filterArgs(Object[] args) {
        if (args == null || args.length == 0) {
            return new Object[0];
        }
        return java.util.Arrays.stream(args)
                .filter(arg -> !(arg instanceof HttpServletRequest))
                .filter(arg -> !(arg instanceof HttpServletResponse))
                .toArray();
    }

    private Long getLong(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        try {
            return Long.valueOf(value.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private String firstNonBlank(String first, String second) {
        return first != null && !first.trim().isEmpty() ? first : second;
    }

    private static class OperationTarget {
        private final String action;
        private final String objectType;
        private final String objectId;

        private OperationTarget(String action, String objectType, String objectId) {
            this.action = action;
            this.objectType = objectType;
            this.objectId = objectId;
        }
    }
}
