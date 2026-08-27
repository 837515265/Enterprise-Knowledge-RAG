package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.ludan.app.entity.KbAuditHistory;

import java.util.List;
import java.util.Map;

/**
 * 审核 Service
 *
 * @author ludan
 */
public interface KbAuditService {

    /**
     * 提交文件级审核（对文件下所有 pending chunk 进行审核）
     *
     * @param kbId           知识库ID
     * @param fileNodeId     文件节点ID
     * @param status         审核结果 approved/rejected/partially_approved
     * @param reviewComment  审核意见
     * @param approvedIds    通过的 chunk IDs
     * @param rejectedIds    驳回的 chunk IDs
     * @param rejectReason   驳回原因
     * @param rejectedReasons 每个 chunk 的驳回原因
     */
    void submitFileAudit(Long kbId, Long fileNodeId, String status, String reviewComment,
                         List<Long> approvedIds, List<Long> rejectedIds, String rejectReason,
                         Map<String, Object> rejectedReasons);

    /**
     * 提交QA审核
     */
    void submitQaAudit(Long kbId, Long qaId, String status, String reviewComment);

    /**
     * 审核历史查询
     */
    Page<KbAuditHistory> getHistory(Map<String, Object> params);
}
