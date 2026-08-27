package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;
import java.util.Map;

/**
 * retrieve-service 混合检索请求体（《当前代码接口完整文档》§5.2）
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagRetrieveQueryRequest {

    @JsonProperty("kb_ids")
    private List<Long> kbIds;

    private String query;

    @JsonProperty("file_node_ids")
    private List<Long> fileNodeIds;

    @JsonProperty("allowed_file_ids")
    private List<Long> allowedFileIds;

    @JsonProperty("top_k")
    private Integer topK;

    private Map<String, Object> filters;

    private Map<String, Object> options;
}
