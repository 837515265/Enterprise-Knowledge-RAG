package com.ludan.app.mapper;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbAuditHistory;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Map;

/**
 * 审核历史 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbAuditHistoryMapper extends SuperMapper<KbAuditHistory> {

    Page<KbAuditHistory> findList(Page<KbAuditHistory> page, @Param("p") Map<String, Object> params);
}
