package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.entity.KbKnowledgeBase;
import com.ludan.app.entity.KbPermissionRule;
import com.ludan.app.mapper.KbKnowledgeBaseMapper;
import com.ludan.app.mapper.KbPermissionRuleMapper;
import com.ludan.app.service.KbPermissionService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 权限管理 Service 实现
 *
 * @author ludan
 */
@Service
@RequiredArgsConstructor
public class KbPermissionServiceImpl
        extends SuperServiceImpl<KbPermissionRuleMapper, KbPermissionRule>
        implements KbPermissionService {

    private final KbKnowledgeBaseMapper knowledgeBaseMapper;

    @Override
    public List<KbPermissionRule> getMembers(Long kbId) {
        return this.list(new LambdaQueryWrapper<KbPermissionRule>()
                .eq(KbPermissionRule::getKbId, kbId)
                .orderByDesc(KbPermissionRule::getCreateTime));
    }

    @Override
    public KbPermissionRule addMember(Long kbId, String ruleType, String targetId, String grantRole) {
        // 去重检查
        long exist = this.count(new LambdaQueryWrapper<KbPermissionRule>()
                .eq(KbPermissionRule::getKbId, kbId)
                .eq(KbPermissionRule::getRuleType, ruleType)
                .eq(KbPermissionRule::getTargetId, targetId)
                .eq(KbPermissionRule::getGrantRole, grantRole));
        if (exist > 0) {
            throw new RuntimeException("该成员/角色已存在相同权限");
        }
        KbPermissionRule rule = new KbPermissionRule();
        rule.setKbId(kbId);
        rule.setRuleType(ruleType);
        rule.setTargetId(targetId);
        rule.setGrantRole(grantRole);
        this.save(rule);
        return rule;
    }

    @Override
    public boolean canUseKb(KbKnowledgeBase kb, String userId) {
        if (kb == null) {
            return false;
        }
        if ("public".equals(kb.getVisibility())) {
            return true;
        }
        if (userId == null || userId.trim().isEmpty()) {
            return false;
        }
        Long cnt = this.count(new LambdaQueryWrapper<KbPermissionRule>()
                .eq(KbPermissionRule::getKbId, kb.getId())
                .eq(KbPermissionRule::getRuleType, "user")
                .eq(KbPermissionRule::getTargetId, userId));
        return cnt != null && cnt > 0;
    }

    @Override
    public List<KbKnowledgeBase> resolveAccessibleKbs(String userId) {
        List<KbKnowledgeBase> kbs = knowledgeBaseMapper.selectList(
                new LambdaQueryWrapper<KbKnowledgeBase>()
                        .eq(KbKnowledgeBase::getStatus, "active"));
        List<KbKnowledgeBase> allowed = new ArrayList<>();
        for (KbKnowledgeBase kb : kbs) {
            if (canUseKb(kb, userId)) {
                allowed.add(kb);
            }
        }
        return allowed;
    }
}
