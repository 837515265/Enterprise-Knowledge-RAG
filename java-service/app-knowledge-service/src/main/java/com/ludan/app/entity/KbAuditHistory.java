package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.Date;

/**
 * 审核历史归档表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_audit_history")
public class KbAuditHistory extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;

    @ApiModelProperty("业务类型 chunk/qa")
    private String bizType;

    @ApiModelProperty("业务上下文ID")
    private Long bizId;

    @ApiModelProperty("本轮裁决 approved/partially_approved/rejected")
    private String status;

    private String reviewer;
    private String reviewerName;
    private String reviewComment;
    private String approvedIds;
    private String rejectedIds;
    private Date reviewedAt;
}
