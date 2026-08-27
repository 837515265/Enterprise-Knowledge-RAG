package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class QaResponse {

    @ApiModelProperty("QA对ID")
    private Long id;

    @ApiModelProperty("问题")
    private String question;

    @ApiModelProperty("答案")
    private String answer;

    @ApiModelProperty("审核状态 pending/approved/rejected")
    private String auditStatus;

    @ApiModelProperty("创建时间")
    private String createTime;
}
