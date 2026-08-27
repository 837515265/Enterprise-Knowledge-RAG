package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * parse-service 单文件解析响应。
 */
@Getter
@Setter
@JsonIgnoreProperties(ignoreUnknown = true)
public class RagParseFileResponse {

    private String status;

    @JsonProperty("task_id")
    private String taskId;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    private String profile;

    @JsonProperty("engine_task_id")
    private String engineTaskId;
}
