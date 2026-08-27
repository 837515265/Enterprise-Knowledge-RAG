package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * 知识库问答对表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_qa_pair")
public class KbQaPair extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;
    private String question;
    private String answer;

    @ApiModelProperty("审核状态 pending/approved/rejected")
    private String auditStatus;

    private String indexSyncStatus;
    private String indexRecordId;
    private String syncErrorMessage;
    private String extendedQuestions;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;
}
