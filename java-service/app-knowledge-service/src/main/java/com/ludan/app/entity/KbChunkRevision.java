package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.central.common.model.BaseEntityFill;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * Chunk 内容版本表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_chunk_revision")
public class KbChunkRevision extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;
    private Long fileNodeId;
    private Long chunkId;
    private Integer revisionNo;
    private String revisionSource;
    private Long baseRevisionId;
    private String content;
    private String summary;
    private String contentForEmbedding;
    private String contentForBm25;
    private String title;
    private String titlePath;
    private Integer pageStart;
    private Integer pageEnd;
    private String blockIds;
    private String bboxJson;
    private String metadataJson;
    private String editorId;
    private String editorName;
    private String editReason;
}
