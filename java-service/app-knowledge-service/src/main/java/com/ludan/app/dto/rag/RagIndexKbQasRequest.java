package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RagIndexKbQasRequest {

    @JsonProperty("kb_id")
    private Long kbId;
}
