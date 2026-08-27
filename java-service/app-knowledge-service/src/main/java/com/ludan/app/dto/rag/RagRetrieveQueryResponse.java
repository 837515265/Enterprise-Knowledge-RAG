package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;
import java.util.Map;

/**
 * retrieve-service 混合检索响应（《当前代码接口完整文档》§5.2）
 */
@Getter
@Setter
@JsonIgnoreProperties(ignoreUnknown = true)
public class RagRetrieveQueryResponse {

    @JsonProperty("kb_id")
    private Long kbId;

    private String query;

    private List<RagRetrieveResultItem> results;

    private Map<String, Object> debug;

    @JsonProperty("llm_context")
    private String llmContext;
}
