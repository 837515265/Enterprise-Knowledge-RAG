package com.ludan.app.dto.req;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * QA审核提交请求体
 *
 * @author ludan
 */
@Data
public class KbQaAuditSubmitReqDTO {

    @ApiModelProperty("审核结果 approved/rejected")
    private String status;

    @ApiModelProperty("审核意见")
    private String reviewComment;
}
