package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

@Data
public class BatchDeleteResponse {

    @ApiModelProperty("成功删除的数量")
    private int deletedCount;
}
