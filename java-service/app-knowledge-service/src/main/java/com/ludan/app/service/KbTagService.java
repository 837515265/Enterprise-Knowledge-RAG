package com.ludan.app.service;

import com.central.common.service.ISuperService;
import com.ludan.app.entity.KbTag;

import java.util.List;

/**
 * 知识库标签 Service
 *
 * @author ludan
 */
public interface KbTagService extends ISuperService<KbTag> {

    /**
     * 查询全部标签
     */
    List<KbTag> findAll();

    /**
     * 创建标签（名称唯一）
     */
    KbTag createTag(String name);
}
