package com.ludan.app.dto.req;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;

/**
 * 创建知识库请求体
 *
 * @author ludan
 */
@Data
public class KbCreateReqDTO {

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

    @ApiModelProperty("默认解析策略配置ID")
    private String parseStrategyConfigId;

    @ApiModelProperty("默认检索策略配置ID")
    private String retrievalConfigId;

    @ApiModelProperty("默认模型配置JSON")
    private String modelProfile;

    @ApiModelProperty("关联标签ID列表")
    private List<Long> tagIds;
}
