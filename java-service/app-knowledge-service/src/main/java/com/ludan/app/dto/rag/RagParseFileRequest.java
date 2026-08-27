package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.Map;

/**
 * parse-service 单文件解析请求体（《当前代码接口完整文档》§2.4）。
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagParseFileRequest {

    @JsonProperty("task_id")
    private Long taskId;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    @JsonProperty("file_id")
    private String fileId;

    private String profile;

    @JsonProperty("parse_generation")
    private String parseGeneration;

    @JsonProperty("index_generation")
    private String indexGeneration;

    @JsonProperty("engine_task_id")
    private String engineTaskId;

    @JsonProperty("parse_strategy_config_id")
    private String parseStrategyConfigId;

    @JsonProperty("model_profile")
    private Map<String, Object> modelProfile;

    @JsonProperty("async_mode")
    private Boolean asyncMode;

    @JsonProperty("return_payload")
    private Boolean returnPayload;

    @JsonProperty("parse_options")
    private Map<String, Object> parseOptions;
}
