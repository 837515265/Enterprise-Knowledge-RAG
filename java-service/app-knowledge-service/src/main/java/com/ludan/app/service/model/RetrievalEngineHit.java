package com.ludan.app.service.model;

import lombok.Getter;
import lombok.Setter;

import java.util.Map;

/**
 * 检索引擎单条命中（对接《当前代码接口完整文档》§5.2 响应 results[]）
 *
 * @author ludan
 */
@Getter
@Setter
public class RetrievalEngineHit {

    private Long chunkId;
    private String indexRecordId;
    private Double score;
    private String snippet;
    private String retrieverType;
    private Map<String, Object> metadata;
    private Object rawData;
}
