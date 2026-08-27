package com.ludan.app.service;

import java.util.List;
import java.util.Map;

/**
 * 解析任务列表查询（转发 app-rag-doc）。
 */
public interface KbParseTaskQueryService {

    List<Map<String, Object>> listParseTasks(String status, Long kbId, Long fileNodeId, Integer limit);
}
