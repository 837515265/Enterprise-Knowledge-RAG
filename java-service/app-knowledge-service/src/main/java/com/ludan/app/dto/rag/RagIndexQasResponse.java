package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

@Data
public class RagIndexQasResponse {

    private String status;

    private String operation;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("index_generation")
    private String indexGeneration;

    @JsonProperty("indexed_qa")
    private Integer indexedQa;
}
