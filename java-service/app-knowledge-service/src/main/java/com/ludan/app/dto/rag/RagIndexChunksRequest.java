package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * retrieve-service Chunk 增量索引请求体（《当前代码接口完整文档》§3.8）。
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagIndexChunksRequest {

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    @JsonProperty("chunk_ids")
    private List<Long> chunkIds;

    @JsonProperty("parse_generation")
    private String parseGeneration;

    @JsonProperty("index_generation")
    private String indexGeneration;

    private String operation;
}
