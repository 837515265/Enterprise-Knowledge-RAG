package com.ludan.app.dto.resp;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.Date;
import java.util.List;

/**
 * 知识库列表项
 *
 * @author ludan
 */
@Data
public class KbListRespDTO {

    @ApiModelProperty("知识库ID")
    private Long id;

    @ApiModelProperty("知识库名称")
    private String name;

    @ApiModelProperty("知识库类型")
    private String type;

    @ApiModelProperty("描述")
    private String description;

    @ApiModelProperty("公开性")
    private String visibility;

    @ApiModelProperty("状态")
    private String status;

    @ApiModelProperty("文件审核开关")
    private Integer fileAuditEnabled;

    @ApiModelProperty("问答审核开关")
    private Integer qaAuditEnabled;

    @ApiModelProperty("成员数")
    private Integer memberCount;

    @ApiModelProperty("文件数")
    private Integer fileCount;

    @ApiModelProperty("待审核文件数")
    private Integer pendingFileCount;

    @ApiModelProperty("待审核问答对数")
    private Integer pendingQaCount;

    @ApiModelProperty("默认解析策略配置ID")
    private String parseStrategyConfigId;

    @ApiModelProperty("默认检索策略配置ID")
    private String retrievalConfigId;

    @ApiModelProperty("默认模型配置JSON")
    private String modelProfile;

    @ApiModelProperty("当前用户在知识库中的角色 owner/member")
    private String role;

    @ApiModelProperty("当前用户是否为知识库所有者")
    private Boolean isOwner;

    @ApiModelProperty("标签列表")
    private List<TagItem> tags;

    @ApiModelProperty("创建人")
    private String createName;

    @ApiModelProperty("创建时间")
    private Date createTime;

    @ApiModelProperty("更新时间")
    private Date updateTime;

    @Data
    public static class TagItem {
        private Long id;
        private String name;
    }
}
