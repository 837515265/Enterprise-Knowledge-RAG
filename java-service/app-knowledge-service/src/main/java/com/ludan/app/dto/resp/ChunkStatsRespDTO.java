package com.ludan.app.dto.resp;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * Chunk 统计响应
 *
 * @author ludan
 */
@Data
public class ChunkStatsRespDTO {

    @ApiModelProperty("总Chunk数")
    private int totalChunkCount;

    @ApiModelProperty("有效Chunk数（已审核启用且未删除）")
    private int availableChunkCount;

    @ApiModelProperty("已删除Chunk数")
    private int deletedChunkCount;
}
