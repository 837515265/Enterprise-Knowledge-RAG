package com.ludan.app.service;

import com.ludan.app.dto.resp.KbSearchFileItemDTO;

import java.util.List;

/**
 * 搜文件（按知识库索引集合检索并聚合为文件维度）
 *
 * @author ludan
 */
public interface KbSearchService {

    /**
     * 在可访问知识库范围内检索文件
     *
     * @param keyword   关键词
     * @param kbId      限定知识库，null 表示在全部可访问且已建索引的库中检索
     * @param fileType  前端筛选：pdf / word / excel，null 表示不过滤
     * @param titleOnly 仅标题匹配（引擎侧用 keyword 模式 + 结果侧过滤）
     */
    List<KbSearchFileItemDTO> searchFiles(String keyword, Long kbId, String fileType, Boolean titleOnly);
}
