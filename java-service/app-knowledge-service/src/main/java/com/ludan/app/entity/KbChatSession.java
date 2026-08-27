package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.Date;

/**
 * 问AI会话表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_chat_session")
public class KbChatSession extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;
    private String scopeType;
    private String scopeKbIds;
    private String userId;
    private String sessionScopeHash;
    private String title;
    private Date lastMessageAt;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;
}
