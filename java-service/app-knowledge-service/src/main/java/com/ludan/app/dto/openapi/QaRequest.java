package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class QaRequest {

    @ApiModelProperty(value = "问题", required = true)
    private String question;

    @ApiModelProperty(value = "答案", required = true)
    private String answer;
}
