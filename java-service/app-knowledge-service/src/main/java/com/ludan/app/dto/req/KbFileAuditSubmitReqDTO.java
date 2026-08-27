package com.ludan.app.dto.req;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 文件级审核提交请求体
 *
 * @author ludan
 */
@Data
public class KbFileAuditSubmitReqDTO {

    @ApiModelProperty("审核结果 approved/rejected/partially_approved")
    private String status;

    @ApiModelProperty("审核意见")
    private String reviewComment;

    @ApiModelProperty("通过的 Chunk ID 列表")
    private List<Long> approvedIds;

    @ApiModelProperty("驳回的 Chunk ID 列表")
    private List<Long> rejectedIds;

    @ApiModelProperty("统一驳回原因")
    private String rejectReason;

    @ApiModelProperty("每个 Chunk 的驳回原因，key 为 Chunk ID")
    private Map<String, Object> rejectedReasons;
}
