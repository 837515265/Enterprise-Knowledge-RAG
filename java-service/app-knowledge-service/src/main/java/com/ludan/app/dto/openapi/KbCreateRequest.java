package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class KbCreateRequest {

    @ApiModelProperty(value = "知识库名称", required = true)
    private String name;

    @ApiModelProperty("知识库描述")
    private String description;

    @ApiModelProperty(value = "知识库类型 business_plan/governance_rule/project_doc/sql_analytics", example = "business_plan")
    private String type;

    @ApiModelProperty(value = "公开性 public/private", example = "public")
    private String visibility;
}
