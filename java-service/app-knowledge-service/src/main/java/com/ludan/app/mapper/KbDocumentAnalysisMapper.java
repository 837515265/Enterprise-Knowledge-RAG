package com.ludan.app.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * 文档结构化解析结果查询。
 *
 * <p>解析服务已经将章节、摘要、知识单元和关系写入独立表，管理端应读取当前解析代际，
 * 而不是仅根据 Chunk 反推文档结构。</p>
 */
@Mapper
public interface KbDocumentAnalysisMapper {

    Map<String, Object> selectFileContext(@Param("kbId") Long kbId, @Param("fileId") Long fileId);

    List<Map<String, Object>> selectChunkTypeStats(@Param("kbId") Long kbId,
                                                    @Param("fileId") Long fileId,
                                                    @Param("parseGeneration") String parseGeneration);

    List<Map<String, Object>> selectSections(@Param("kbId") Long kbId,
                                              @Param("fileId") Long fileId,
                                              @Param("parseGeneration") String parseGeneration);

    List<Map<String, Object>> selectSectionSummaries(@Param("kbId") Long kbId,
                                                      @Param("fileId") Long fileId,
                                                      @Param("parseGeneration") String parseGeneration);

    List<Map<String, Object>> selectKnowledgeUnits(@Param("kbId") Long kbId,
                                                    @Param("fileId") Long fileId,
                                                    @Param("parseGeneration") String parseGeneration);

    List<Map<String, Object>> selectAnchors(@Param("kbId") Long kbId,
                                            @Param("fileId") Long fileId,
                                            @Param("parseGeneration") String parseGeneration);

    List<Map<String, Object>> selectRelations(@Param("kbId") Long kbId,
                                              @Param("fileId") Long fileId,
                                              @Param("parseGeneration") String parseGeneration);
}
