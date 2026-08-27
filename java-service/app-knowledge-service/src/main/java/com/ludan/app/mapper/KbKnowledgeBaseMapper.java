package com.ludan.app.mapper;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.db.mapper.SuperMapper;
import com.ludan.app.dto.resp.KbListRespDTO;
import com.ludan.app.entity.KbKnowledgeBase;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Map;

/**
 * 知识库主表 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbKnowledgeBaseMapper extends SuperMapper<KbKnowledgeBase> {

    Page<KbListRespDTO> findList(Page<KbListRespDTO> page, @Param("p") Map<String, Object> params);
}
