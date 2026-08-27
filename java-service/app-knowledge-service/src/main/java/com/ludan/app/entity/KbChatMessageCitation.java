package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.central.common.model.BaseEntityFill;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

/**
 * 消息召回/引用明细表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_chat_message_citation")
public class KbChatMessageCitation extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long messageId;
    private Long sessionId;
    private Long kbId;
    private String bizType;
    private Long bizId;
    private Long fileNodeId;
    private Integer rankNo;
    private BigDecimal score;
    private String retrieverType;
    private Integer isCited;
    private Integer citeIndex;
    private String snippet;
    private Integer pageNum;
    private String metadataJson;
}
