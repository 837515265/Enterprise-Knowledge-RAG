package com.ludan.app.service;

import com.central.common.service.ISuperService;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.entity.KbPermissionRule;

import java.util.List;

/**
 * 权限管理 Service
 *
 * @author ludan
 */
public interface KbPermissionService extends ISuperService<KbPermissionRule> {

    /**
     * 查询知识库成员列表
     */
    List<KbPermissionRule> getMembers(Long kbId);

    /**
     * 添加成员
     */
    KbPermissionRule addMember(Long kbId, String ruleType, String targetId, String grantRole);

    /**
     * 判断用户是否有权访问指定知识库。
     * <p>公开库直接放行；私有库需 userId 非空且在 kb_permission_rule 中有记录。</p>
     */
    boolean canUseKb(KbKnowledgeBase kb, String userId);

    /**
     * 查询用户可访问的所有 active 知识库（公开库 ∪ 有权限的私有库）。
     */
    List<KbKnowledgeBase> resolveAccessibleKbs(String userId);
}
