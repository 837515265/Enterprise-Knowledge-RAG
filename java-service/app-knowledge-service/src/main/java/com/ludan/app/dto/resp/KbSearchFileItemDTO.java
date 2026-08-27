package com.ludan.app.dto.resp;

import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Getter;
import lombok.Setter;

/**
 * 搜文件单条结果（按文件聚合展示）
 *
 * @author ludan
 */
@Getter
@Setter
@ApiModel("搜文件结果项")
public class KbSearchFileItemDTO {

    @ApiModelProperty("文件节点 ID（kb_file_node.id）")
    private Long id;

    @ApiModelProperty("对象存储文件 ID，用于预览/下载")
    private String fileId;

    @ApiModelProperty("所属知识库 ID")
    private Long kbId;

    @ApiModelProperty("展示标题，优先原始文件名")
    private String title;

    @ApiModelProperty("同 title，兼容前端")
    private String name;

    @ApiModelProperty("知识库名称")
    private String kbName;

    @ApiModelProperty("扩展名或类型摘要，如 pdf")
    private String fileType;

    @ApiModelProperty("可读文件大小")
    private String size;

    @ApiModelProperty("更新时间展示")
    private String updateTime;

    @ApiModelProperty("命中片段")
    private String snippet;

    @ApiModelProperty("摘要/描述")
    private String description;

    @ApiModelProperty("检索综合得分 0~1")
    private Double score;
}
