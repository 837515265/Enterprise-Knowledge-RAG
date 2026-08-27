package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbFileTask;
import org.apache.ibatis.annotations.Mapper;

/**
 * 文件解析任务 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbFileTaskMapper extends SuperMapper<KbFileTask> {
}
