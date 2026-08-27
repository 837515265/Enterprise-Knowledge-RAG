package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * Chunk 主数据表（当前态 SSOT）
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_chunk")
public class KbChunk extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;
    private Long fileNodeId;
    private Integer seqNo;
    private String content;
    private String summary;
    private Integer enabled;

    @ApiModelProperty("审核状态 pending/approved/rejected")
    private String auditStatus;
    private String rejectReason;
    private String indexRecordId;
    private String indexSyncStatus;
    private String syncErrorMsg;
    private Long publishedRevisionId;
    private Long latestRevisionId;
    private String parseGeneration;
    private String indexGeneration;
    private String contentHash;
    @TableField(exist = false)
    private String title;

    @TableField(exist = false)
    private String titlePath;
    private Integer pageStart;
    private Integer pageEnd;
    private String chunkType;
    private String sectionType;
    private String sectionId;
    private String chunkGroupId;
    private String blockIds;
    private String metadataJson;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;
}
