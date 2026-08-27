package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.entity.KbRetrievalStrategyConfig;
import com.ludan.app.mapper.KbRetrievalStrategyConfigMapper;
import com.ludan.app.service.KbRetrievalStrategyConfigService;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 检索策略配置 Service 实现
 *
 * @author ludan
 */
@Service
public class KbRetrievalStrategyConfigServiceImpl
        extends SuperServiceImpl<KbRetrievalStrategyConfigMapper, KbRetrievalStrategyConfig>
        implements KbRetrievalStrategyConfigService {

    @Override
    public List<KbRetrievalStrategyConfig> findList(Map<String, Object> params) {
        Long kbId = toLong(params.get("kbId"));
        String scopeType = toTrimmedString(params.get("scopeType"));
        String status = toTrimmedString(params.get("status"));

        LambdaQueryWrapper<KbRetrievalStrategyConfig> wrapper = new LambdaQueryWrapper<>();
        if (kbId != null) {
            wrapper.and(w -> w.eq(KbRetrievalStrategyConfig::getScopeType, "template")
                    .or()
                    .eq(KbRetrievalStrategyConfig::getKbId, kbId));
        }
        if (!isBlank(scopeType)) {
            wrapper.eq(KbRetrievalStrategyConfig::getScopeType, scopeType);
        }
        if (!isBlank(status)) {
            wrapper.eq(KbRetrievalStrategyConfig::getStatus, status);
        }
        wrapper.orderByDesc(KbRetrievalStrategyConfig::getUpdateTime);
        return this.list(wrapper);
    }

    @Override
    public KbRetrievalStrategyConfig createConfig(KbRetrievalStrategyConfig config) {
        validateConfig(config);
        if (isBlank(config.getId())) {
            config.setId(UUID.randomUUID().toString().replace("-", ""));
        }
        if (isBlank(config.getScopeType())) {
            config.setScopeType("template");
        }
        if (isBlank(config.getStatus())) {
            config.setStatus("active");
        }
        this.save(config);
        return config;
    }

    @Override
    public void updateConfig(String id, KbRetrievalStrategyConfig config) {
        KbRetrievalStrategyConfig current = this.getById(id);
        if (current == null) {
            throw new RuntimeException("检索策略配置不存在");
        }
        config.setId(id);
        this.updateById(config);
    }

    /**
     * 校验策略名称和配置 JSON，避免创建不可用策略。
     */
    private void validateConfig(KbRetrievalStrategyConfig config) {
        if (config == null || isBlank(config.getName())) {
            throw new RuntimeException("检索策略名称不能为空");
        }
        if (isBlank(config.getConfigJson())) {
            throw new RuntimeException("检索策略配置不能为空");
        }
    }

    private Long toLong(Object value) {
        if (value == null || isBlank(value.toString())) {
            return null;
        }
        return Long.valueOf(value.toString());
    }

    private String toTrimmedString(Object value) {
        return value == null ? null : value.toString().trim();
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
