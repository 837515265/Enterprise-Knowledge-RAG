package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * rag-doc KB 级索引重建请求体。
 * POST /api/v1/index/kb/rebuild
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagIndexKbRebuildRequest {

    @JsonProperty("kb_id")
    private Long kbId;
}
