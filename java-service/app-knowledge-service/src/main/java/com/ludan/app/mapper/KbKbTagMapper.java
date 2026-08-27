package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbKbTag;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * 知识库-标签关联 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbKbTagMapper extends SuperMapper<KbKbTag> {

    /**
     * 根据知识库ID查询关联的标签ID列表
     */
    List<Long> selectTagIdsByKbId(@Param("kbId") Long kbId);

    /**
     * 根据知识库ID删除所有关联
     */
    int deleteByKbId(@Param("kbId") Long kbId);
}
