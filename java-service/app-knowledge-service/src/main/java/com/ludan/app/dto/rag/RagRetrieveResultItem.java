package com.ludan.app.dto.rag;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * retrieve-service 单条检索结果（字段随 source 不同略有差异）
 */
@Getter
@Setter
public class RagRetrieveResultItem {

    private String source;

    private Double score;

    @JsonProperty("rerank_score")
    private Double rerankScore;

    @JsonProperty("kb_id")
    private Long kbId;

    @JsonProperty("file_node_id")
    private Long fileNodeId;

    @JsonProperty("chunk_id")
    private Long chunkId;

    @JsonProperty("chunk_type")
    private String chunkType;

    @JsonProperty("file_center_file_id")
    private String fileCenterFileId;

    @JsonProperty("visual_asset_id")
    private String visualAssetId;

    @JsonProperty("field_id")
    private Long fieldId;

    @JsonProperty("qa_id")
    private Long qaId;

    private String title;

    private String content;

    private Integer rank;

    @JsonProperty("route_name")
    private String routeName;

    @JsonProperty("route_names")
    private List<String> routeNames;

    @JsonProperty("hit_type")
    private String hitType;

    @JsonProperty("field_code")
    private String fieldCode;

    @JsonProperty("field_name_cn")
    private String fieldNameCn;

    @JsonProperty("value_text")
    private String valueText;

    @JsonProperty("evidence_quote")
    private String evidenceQuote;

    @JsonProperty("evidence_text")
    private String evidenceText;

    @JsonProperty("evidence_chain")
    private List<String> evidenceChain;

    @JsonProperty("graph_path")
    private Map<String, Object> graphPath;

    private String reason;

    @JsonProperty("page_no")
    private Integer pageNo;

    @JsonProperty("raw_items")
    private List<Map<String, Object>> rawItems;

    private final Map<String, Object> extras = new HashMap<>();

    @JsonAnySetter
    public void setExtra(String key, Object value) {
        extras.put(key, value);
    }

    public Map<String, Object> getExtras() {
        return extras;
    }
}
