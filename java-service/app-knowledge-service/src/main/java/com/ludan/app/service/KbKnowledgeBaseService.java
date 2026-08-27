package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.ISuperService;
import com.ludan.app.dto.req.KbCreateReqDTO;
import com.ludan.app.dto.req.KbUpdateReqDTO;
import com.ludan.app.dto.resp.KbListRespDTO;
import com.ludan.app.dto.resp.KbSimpleItemDTO;
import com.ludan.app.entity.KbKnowledgeBase;

import java.util.List;
import java.util.Map;

/**
 * 知识库管理 Service
 *
 * @author ludan
 */
public interface KbKnowledgeBaseService extends ISuperService<KbKnowledgeBase> {

    /**
     * 分页查询知识库列表
     */
    Page<KbListRespDTO> findList(Map<String, Object> params);

    /**
     * 创建知识库（含标签关联）
     */
    KbKnowledgeBase createKb(KbCreateReqDTO reqDTO);

    /**
     * 更新知识库（含标签关联全量覆盖）
     */
    void updateKb(Long kbId, KbUpdateReqDTO reqDTO);

    /**
     * 查询知识库详情（补充标签信息）
     */
    KbListRespDTO getKbDetail(Long kbId);

    /**
     * 按用户查询可访问的知识库简要列表（id + name），userId 为空时仅返回公开库。
     */
    List<KbSimpleItemDTO> getSimpleList(String userId);
}
