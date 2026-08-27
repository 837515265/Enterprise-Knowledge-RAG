package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;

@Data
public class BatchDeleteRequest {

    @ApiModelProperty(value = "待删除 ID 列表", required = true)
    private List<Long> ids;
}
