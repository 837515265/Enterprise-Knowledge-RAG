package com.ludan.app.feign;

import com.ludan.app.config.ParseEngineProperties;
import com.ludan.app.dto.rag.RagParseFileRequest;
import com.ludan.app.dto.rag.RagParseFileResponse;
import feign.RequestInterceptor;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.Map;

/**
 * 调用 AI 引擎 parse-service 能力。服务名与检索保持一致。
 */
@FeignClient(
        contextId = "appRagDocParseClient",
        name = "${parse-engine.service-name:app-rag-doc}",
        configuration = AppRagDocParseClient.FeignClientConfiguration.class
)
public interface AppRagDocParseClient {

    @PostMapping(value = "/api/v1/parse/files", consumes = MediaType.APPLICATION_JSON_VALUE)
    RagParseFileResponse submitParseFile(@RequestBody RagParseFileRequest body);

    @GetMapping(value = "/api/v1/parse/tasks/{taskId}")
    Map<String, Object> queryParseTask(@PathVariable("taskId") Long taskId);

    @GetMapping(value = "/api/v1/parse/tasks")
    Object listParseTasks(@RequestParam Map<String, Object> params);

    class FeignClientConfiguration {
        @Bean
        public RequestInterceptor parseApiTokenInterceptor(ParseEngineProperties parseEngineProperties) {
            return template -> {
                String token = parseEngineProperties.getApiToken();
                if (StringUtils.hasText(token)) {
                    template.header("X-API-Token", token.trim());
                }
            };
        }
    }
}
