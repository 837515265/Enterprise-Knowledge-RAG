package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
public class RagIndexQasRequest {

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("qa_ids")
    private List<Long> qaIds;

    @JsonProperty("index_generation")
    private String indexGeneration;

    private String operation;
}
