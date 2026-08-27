package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.Map;

/**
 * retrieve-service 文件级索引请求体（《当前代码接口完整文档》§3.6）。
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagIndexFileRequest {

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    @JsonProperty("parse_generation")
    private String parseGeneration;

    @JsonProperty("index_generation")
    private String indexGeneration;

    private String operation = "rebuild";

    @JsonProperty("async_mode")
    private Boolean asyncMode;

    @JsonProperty("index_options")
    private Map<String, Object> indexOptions;
}
