package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * 文件节点表（文件夹树 + 文件）
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_file_node")
public class KbFileNode extends BaseEntityFill {

    @ApiModelProperty("主键: 文件类型=文件ID, 文件夹类型=雪花ID")
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    @ApiModelProperty("所属知识库ID")
    private Long kbId;

    @ApiModelProperty("父节点ID")
    private Long parentId;

    @ApiModelProperty("节点类型 folder/file")
    private String nodeType;

    @ApiModelProperty("节点名称")
    private String name;

    @ApiModelProperty("原始文件名")
    private String originalName;

    @ApiModelProperty("对象存储中的原始文件ID")
    private String fileId;

    @ApiModelProperty("文件字节数")
    private Long fileSize;

    @ApiModelProperty("MIME类型")
    private String mimeType;

    @ApiModelProperty("扩展名")
    private String fileExt;

    @ApiModelProperty("文件SHA-256")
    private String fileHash;

    @ApiModelProperty("解析策略配置ID")
    private String parseStrategyConfigId;

    @ApiModelProperty("是否开启多模态解析 0/1（图文文档提图 + VLM 描述）")
    private Integer multimodalEnabled;

    @ApiModelProperty("解析状态 none/parsing/parsed/failed")
    private String parseStatus;

    @ApiModelProperty("索引状态 none/indexing/synced/failed")
    private String indexStatus;

    @ApiModelProperty("当前成功解析代际")
    private String currentParseGeneration;

    @ApiModelProperty("当前已发布索引代际")
    private String currentIndexGeneration;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;

    @ApiModelProperty("子节点")
    @TableField(exist = false)
    private List<KbFileNode> children;

    @ApiModelProperty("待审核Chunk数量")
    @TableField(exist = false)
    private Integer pendingChunkCount;

    @ApiModelProperty("聚合审核状态 pending=存在待审核Chunk")
    @TableField(exist = false)
    private String auditStatus;

    @ApiModelProperty("最近一次解析失败原因")
    @TableField(exist = false)
    private String parseErrorMsg;
}
