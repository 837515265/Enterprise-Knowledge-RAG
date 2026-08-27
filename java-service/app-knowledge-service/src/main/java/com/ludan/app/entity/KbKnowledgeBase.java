package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * 知识库主表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_knowledge_base")
public class KbKnowledgeBase extends BaseEntityFill {

    @ApiModelProperty("主键，雪花ID")
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    @ApiModelProperty("知识库名称")
    private String name;

    @ApiModelProperty("知识库类型 business_plan/governance_rule/project_doc/sql_analytics 等")
    private String type;

    @ApiModelProperty("知识库描述")
    private String description;

    @ApiModelProperty("公开性 public/private")
    private String visibility;

    @ApiModelProperty("文件审核开关 0=关 1=开")
    private Integer fileAuditEnabled;

    @ApiModelProperty("问答审核开关 0=关 1=开")
    private Integer qaAuditEnabled;

    @ApiModelProperty("状态 active/archived")
    private String status;

    @ApiModelProperty("检索引擎索引集合ID")
    private String indexCollectionId;

    @ApiModelProperty("权限命中成员数缓存")
    private Integer memberCount;

    @ApiModelProperty("默认解析策略配置ID")
    private String parseStrategyConfigId;

    @ApiModelProperty("默认检索策略配置ID")
    private String retrievalConfigId;

    @ApiModelProperty("默认模型配置引用JSON")
    private String modelProfile;

    @TableField("del_flag")
    @TableLogic
    private Integer delFlag;
}
