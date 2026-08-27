package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * retrieve-service 文件级索引响应。
 */
@Getter
@Setter
@JsonIgnoreProperties(ignoreUnknown = true)
public class RagIndexFileResponse {

    private String status;

    @JsonProperty("task_id")
    private String taskId;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    private String operation;

    @JsonProperty("indexed_chunks")
    private Integer indexedChunks;
}
