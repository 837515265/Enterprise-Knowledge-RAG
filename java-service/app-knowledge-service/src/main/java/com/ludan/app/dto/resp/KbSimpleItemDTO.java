package com.ludan.app.dto.resp;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * 知识库简要信息（id + name），用于轻量列表选择器。
 *
 * @author ludan
 */
@Data
public class KbSimpleItemDTO {

    @ApiModelProperty("知识库ID")
    private Long id;

    @ApiModelProperty("知识库名称")
    private String name;
}
