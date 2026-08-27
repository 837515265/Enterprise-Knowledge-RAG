package com.ludan.app.service;

import com.ludan.app.mapper.KbDocumentAnalysisMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 聚合当前解析代际的文档结构化结果。
 */
@Service
@RequiredArgsConstructor
public class KbDocumentAnalysisService {

    private final KbDocumentAnalysisMapper analysisMapper;

    public Map<String, Object> getAnalysis(Long kbId, Long fileId) {
        Map<String, Object> file = analysisMapper.selectFileContext(kbId, fileId);
        if (file == null || file.isEmpty()) {
            throw new RuntimeException("文件不存在");
        }

        String parseGeneration = valueAsString(file.get("parseGeneration"));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("file", file);
        if (parseGeneration == null || parseGeneration.isEmpty()) {
            result.put("chunkTypeStats", Collections.emptyList());
            result.put("sections", Collections.emptyList());
            result.put("summaries", Collections.emptyList());
            result.put("knowledgeUnits", Collections.emptyList());
            result.put("anchors", Collections.emptyList());
            result.put("relations", Collections.emptyList());
            return result;
        }

        result.put("chunkTypeStats", analysisMapper.selectChunkTypeStats(kbId, fileId, parseGeneration));
        result.put("sections", analysisMapper.selectSections(kbId, fileId, parseGeneration));
        result.put("summaries", analysisMapper.selectSectionSummaries(kbId, fileId, parseGeneration));
        result.put("knowledgeUnits", analysisMapper.selectKnowledgeUnits(kbId, fileId, parseGeneration));
        result.put("anchors", analysisMapper.selectAnchors(kbId, fileId, parseGeneration));
        result.put("relations", analysisMapper.selectRelations(kbId, fileId, parseGeneration));
        return result;
    }

    private String valueAsString(Object value) {
        return value == null ? null : value.toString();
    }
}
