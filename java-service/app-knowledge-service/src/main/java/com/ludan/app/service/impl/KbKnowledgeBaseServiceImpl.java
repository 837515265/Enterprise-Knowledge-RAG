package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.dto.req.KbCreateReqDTO;
import com.ludan.app.dto.req.KbUpdateReqDTO;
import com.ludan.app.dto.resp.KbListRespDTO;
import com.ludan.app.dto.resp.KbSimpleItemDTO;
import com.ludan.app.entity.KbKbTag;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.entity.KbTag;
import com.ludan.app.mapper.KbKbTagMapper;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.mapper.KbTagMapper;
import com.ludan.app.service.KbKnowledgeBaseService;
import com.ludan.app.service.KbPermissionService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.apache.commons.collections4.MapUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import javax.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 知识库管理 Service 实现
 *
 * @author ludan
 */
@Service
@RequiredArgsConstructor
public class KbKnowledgeBaseServiceImpl
        extends SuperServiceImpl<KbKnowledgeBaseMapper, KbKnowledgeBase>
        implements KbKnowledgeBaseService {

    private final KbKbTagMapper kbKbTagMapper;
    private final KbTagMapper kbTagMapper;
    private final KbPermissionService permissionService;
    private final ObjectMapper objectMapper;

    @Override
    public Page<KbListRespDTO> findList(Map<String, Object> params) {
        params.put("currentUserId", resolveCurrentUserId());
        Page<KbListRespDTO> page = new Page<>(
                MapUtils.getInteger(params, "pageNo", 1),
                MapUtils.getInteger(params, "pageSize", 10)
        );
        Page<KbListRespDTO> result = baseMapper.findList(page, params);

        // 批量填充标签
        if (result.getRecords() != null && !result.getRecords().isEmpty()) {
            for (KbListRespDTO dto : result.getRecords()) {
                dto.setTags(getTagsByKbId(dto.getId()));
            }
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public KbKnowledgeBase createKb(KbCreateReqDTO reqDTO) {
        KbKnowledgeBase kb = new KbKnowledgeBase();
        kb.setName(reqDTO.getName());
        kb.setType(reqDTO.getType());
        kb.setDescription(reqDTO.getDescription());
        kb.setVisibility(reqDTO.getVisibility() != null ? reqDTO.getVisibility() : "private");
        kb.setFileAuditEnabled(reqDTO.getFileAuditEnabled() != null ? reqDTO.getFileAuditEnabled() : 0);
        kb.setQaAuditEnabled(reqDTO.getQaAuditEnabled() != null ? reqDTO.getQaAuditEnabled() : 0);
        kb.setParseStrategyConfigId(normalizeBlank(reqDTO.getParseStrategyConfigId()));
        kb.setRetrievalConfigId(normalizeBlank(reqDTO.getRetrievalConfigId()));
        kb.setModelProfile(normalizeModelProfile(reqDTO.getModelProfile()));
        kb.setStatus("active");
        kb.setMemberCount(0);
        this.save(kb);

        String creatorUserId = resolveCurrentUserId();
        if (creatorUserId != null) {
            permissionService.addMember(kb.getId(), "user", creatorUserId, "admin");
            kb.setMemberCount(1);
            this.updateById(kb);
        }

        // 保存标签关联
        saveTagRelations(kb.getId(), reqDTO.getTagIds());

        return kb;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateKb(Long kbId, KbUpdateReqDTO reqDTO) {
        KbKnowledgeBase kb = this.getById(kbId);
        if (kb == null) {
            throw new RuntimeException("知识库不存在");
        }
        if (reqDTO.getName() != null) {
            kb.setName(reqDTO.getName());
        }
        if (reqDTO.getType() != null) {
            kb.setType(normalizeBlank(reqDTO.getType()));
        }
        if (reqDTO.getDescription() != null) {
            kb.setDescription(reqDTO.getDescription());
        }
        if (reqDTO.getVisibility() != null) {
            kb.setVisibility(reqDTO.getVisibility());
        }
        if (reqDTO.getFileAuditEnabled() != null) {
            kb.setFileAuditEnabled(reqDTO.getFileAuditEnabled());
        }
        if (reqDTO.getQaAuditEnabled() != null) {
            kb.setQaAuditEnabled(reqDTO.getQaAuditEnabled());
        }
        if (reqDTO.getParseStrategyConfigId() != null) {
            kb.setParseStrategyConfigId(normalizeBlank(reqDTO.getParseStrategyConfigId()));
        }
        if (reqDTO.getRetrievalConfigId() != null) {
            kb.setRetrievalConfigId(normalizeBlank(reqDTO.getRetrievalConfigId()));
        }
        if (reqDTO.getModelProfile() != null) {
            kb.setModelProfile(normalizeModelProfile(reqDTO.getModelProfile()));
        }
        this.updateById(kb);

        // 全量覆盖标签关联
        if (reqDTO.getTagIds() != null) {
            kbKbTagMapper.deleteByKbId(kbId);
            saveTagRelations(kbId, reqDTO.getTagIds());
        }
    }

    @Override
    public KbListRespDTO getKbDetail(Long kbId) {
        KbKnowledgeBase kb = this.getById(kbId);
        if (kb == null) {
            return null;
        }
        KbListRespDTO dto = new KbListRespDTO();
        dto.setId(kb.getId());
        dto.setName(kb.getName());
        dto.setType(kb.getType());
        dto.setDescription(kb.getDescription());
        dto.setVisibility(kb.getVisibility());
        dto.setStatus(kb.getStatus());
        dto.setFileAuditEnabled(kb.getFileAuditEnabled());
        dto.setQaAuditEnabled(kb.getQaAuditEnabled());
        dto.setMemberCount(kb.getMemberCount());
        dto.setParseStrategyConfigId(kb.getParseStrategyConfigId());
        dto.setRetrievalConfigId(kb.getRetrievalConfigId());
        dto.setModelProfile(kb.getModelProfile());
        dto.setIsOwner(isOwner(kb.getId(), kb.getCreator(), resolveCurrentUserId()));
        dto.setRole(Boolean.TRUE.equals(dto.getIsOwner()) ? "owner" : null);
        dto.setCreateName(kb.getCreateName());
        dto.setCreateTime(kb.getCreateTime());
        dto.setUpdateTime(kb.getUpdateTime());
        dto.setTags(getTagsByKbId(kbId));
        return dto;
    }

    /**
     * 查询指定知识库的标签列表
     */
    private List<KbListRespDTO.TagItem> getTagsByKbId(Long kbId) {
        List<Long> tagIds = kbKbTagMapper.selectTagIdsByKbId(kbId);
        if (tagIds == null || tagIds.isEmpty()) {
            return Collections.emptyList();
        }
        List<KbTag> tags = kbTagMapper.selectBatchIds(tagIds);
        return tags.stream().map(t -> {
            KbListRespDTO.TagItem item = new KbListRespDTO.TagItem();
            item.setId(t.getId());
            item.setName(t.getName());
            return item;
        }).collect(Collectors.toList());
    }

    /**
     * 批量保存知识库-标签关联
     */
    private void saveTagRelations(Long kbId, List<Long> tagIds) {
        if (tagIds == null || tagIds.isEmpty()) {
            return;
        }
        for (Long tagId : tagIds) {
            KbKbTag rel = new KbKbTag();
            rel.setKbId(kbId);
            rel.setTagId(tagId);
            kbKbTagMapper.insert(rel);
        }
    }

    /**
     * 校验模型配置 JSON，空字符串按未配置处理。
     */
    private String normalizeModelProfile(String modelProfile) {
        String normalized = normalizeBlank(modelProfile);
        if (normalized == null) {
            return null;
        }
        try {
            objectMapper.readTree(normalized);
            return normalized;
        } catch (Exception e) {
            throw new RuntimeException("模型配置JSON格式不正确", e);
        }
    }

    private String normalizeBlank(String value) {
        return value == null || value.trim().isEmpty() ? null : value.trim();
    }

    private boolean isOwner(Long kbId, String creator, String currentUserId) {
        if (currentUserId == null) {
            return false;
        }
        if (currentUserId.equals(creator)) {
            return true;
        }
        return permissionService.count(new LambdaQueryWrapper<com.ludan.app.entity.KbPermissionRule>()
                .eq(com.ludan.app.entity.KbPermissionRule::getKbId, kbId)
                .eq(com.ludan.app.entity.KbPermissionRule::getRuleType, "user")
                .eq(com.ludan.app.entity.KbPermissionRule::getTargetId, currentUserId)
                .eq(com.ludan.app.entity.KbPermissionRule::getGrantRole, "admin")) > 0;
    }

    private String resolveCurrentUserId() {
        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attributes == null) {
            return null;
        }
        HttpServletRequest request = attributes.getRequest();
        String userId = request.getHeader("x-userid-header");
        return userId == null || userId.trim().isEmpty() ? null : userId.trim();
    }

    @Override
    public List<KbSimpleItemDTO> getSimpleList(String userId) {
        return permissionService.resolveAccessibleKbs(userId).stream()
                .map(kb -> {
                    KbSimpleItemDTO dto = new KbSimpleItemDTO();
                    dto.setId(kb.getId());
                    dto.setName(kb.getName());
                    return dto;
                })
                .collect(Collectors.toList());
    }
}
