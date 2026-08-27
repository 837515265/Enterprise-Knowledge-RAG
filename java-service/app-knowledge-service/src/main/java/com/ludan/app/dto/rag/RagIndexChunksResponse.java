package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * retrieve-service Chunk 增量索引响应体（《当前代码接口完整文档》§3.8）。
 */
@Getter
@Setter
public class RagIndexChunksResponse {

    private String status;

    private String operation;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    @JsonProperty("index_generation")
    private String indexGeneration;

    @JsonProperty("indexed_chunks")
    private Integer indexedChunks;

    @JsonProperty("indexed_fields")
    private Integer indexedFields;

    @JsonProperty("graph_rebuilt")
    private Boolean graphRebuilt;
}
