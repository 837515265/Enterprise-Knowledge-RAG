package com.ludan.app.mapper;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbQaPair;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Map;

/**
 * 问答对 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbQaPairMapper extends SuperMapper<KbQaPair> {

    Page<KbQaPair> findList(Page<KbQaPair> page, @Param("p") Map<String, Object> params);
}
