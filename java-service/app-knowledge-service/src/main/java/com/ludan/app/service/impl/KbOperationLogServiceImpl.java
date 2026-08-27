package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.entity.KbOperationLog;
import com.ludan.app.mapper.KbOperationLogMapper;
import com.ludan.app.service.KbOperationLogService;
import org.apache.commons.collections4.MapUtils;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * 操作日志 Service 实现
 *
 * @author ludan
 */
@Service
public class KbOperationLogServiceImpl
        extends SuperServiceImpl<KbOperationLogMapper, KbOperationLog>
        implements KbOperationLogService {

    @Override
    public Page<KbOperationLog> findList(Map<String, Object> params) {
        Page<KbOperationLog> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 10)
        );
        return baseMapper.findList(page, params);
    }

    @Override
    public void log(Long kbId, Long operatorId, String action, String objectType,
                    String objectId, String summary, String detailJson) {
        KbOperationLog log = new KbOperationLog();
        log.setKbId(kbId);
        log.setOperatorId(operatorId);
        log.setAction(action);
        log.setObjectType(objectType);
        log.setObjectId(objectId);
        log.setSummary(summary);
        log.setDetailJson(detailJson);
        this.save(log);
    }
}
