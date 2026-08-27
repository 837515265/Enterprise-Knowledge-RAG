package com.ludan.app.service;

import com.central.common.service.ISuperService;
import com.ludan.app.entity.KbRetrievalStrategyConfig;

import java.util.List;
import java.util.Map;

/**
 * 检索策略配置 Service
 *
 * @author ludan
 */
public interface KbRetrievalStrategyConfigService extends ISuperService<KbRetrievalStrategyConfig> {

    /**
     * 查询策略配置，传入 kbId 时返回模板与该知识库自定义配置。
     */
    List<KbRetrievalStrategyConfig> findList(Map<String, Object> params);

    /**
     * 创建策略配置并补齐默认字段。
     */
    KbRetrievalStrategyConfig createConfig(KbRetrievalStrategyConfig config);

    /**
     * 更新策略配置。
     */
    void updateConfig(String id, KbRetrievalStrategyConfig config);
}
