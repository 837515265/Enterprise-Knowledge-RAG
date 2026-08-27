package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@JsonIgnoreProperties(ignoreUnknown = true)
public class RagIndexKbQasResponse {

    private String status;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("index_generation")
    private String indexGeneration;

    @JsonProperty("qa_count")
    private Integer qaCount;

    @JsonProperty("indexed_qa")
    private Integer indexedQa;
}
