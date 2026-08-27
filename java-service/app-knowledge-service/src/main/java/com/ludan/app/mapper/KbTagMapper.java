package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbTag;
import org.apache.ibatis.annotations.Mapper;

/**
 * 知识库标签 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbTagMapper extends SuperMapper<KbTag> {
}
