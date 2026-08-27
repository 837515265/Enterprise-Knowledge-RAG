package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.Date;
import java.util.List;
import java.util.Map;

/**
 * 问AI会话消息表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_chat_message")
public class KbChatMessage extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long sessionId;
    private Long kbId;
    private String role;
    private Integer seqNo;
    private String content;
    private String status;
    private String tokenUsage;
    private Long parentMessageId;
    private String feedback;
    private String feedbackComment;
    private String errorMsg;
    private String traceId;
    private Date finishedAt;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;

    @TableField(exist = false)
    private List<Map<String, Object>> citations;
}
