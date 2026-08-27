package com.ludan.app.mapper;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbOperationLog;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Map;

/**
 * 操作日志 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbOperationLogMapper extends SuperMapper<KbOperationLog> {

    Page<KbOperationLog> findList(Page<KbOperationLog> page, @Param("p") Map<String, Object> params);
}
