package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class DocumentResponse {

    @ApiModelProperty("文件中心 fileId")
    private String fileId;

    @ApiModelProperty("展示名称")
    private String fileName;

    @ApiModelProperty("处理状态 SUCCESS/DUPLICATE/FAILED")
    private String status;

    @ApiModelProperty("知识库文件节点ID，可用于后续删除/重解析")
    private Long fileNodeId;

    @ApiModelProperty("处理结果说明")
    private String message;
}
