package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.ISuperService;
import com.ludan.app.entity.KbOperationLog;

import java.util.Map;

/**
 * 操作日志 Service
 *
 * @author ludan
 */
public interface KbOperationLogService extends ISuperService<KbOperationLog> {

    Page<KbOperationLog> findList(Map<String, Object> params);

    /**
     * 记录操作日志
     */
    void log(Long kbId, Long operatorId, String action, String objectType,
             String objectId, String summary, String detailJson);
}
