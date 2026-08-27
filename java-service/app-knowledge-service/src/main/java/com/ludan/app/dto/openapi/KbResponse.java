package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class KbResponse {

    @ApiModelProperty("知识库ID")
    private Long id;

    @ApiModelProperty("知识库名称")
    private String name;

    @ApiModelProperty("知识库类型")
    private String type;

    @ApiModelProperty("公开性 public/private")
    private String visibility;

    @ApiModelProperty("创建时间")
    private String createTime;
}
