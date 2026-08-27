package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * 文件解析与索引任务表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_file_task")
public class KbFileTask extends BaseEntityFill {

    @ApiModelProperty("主键，任务ID")
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    @ApiModelProperty("知识库ID")
    private Long kbId;

    @ApiModelProperty("对应kb_file_node.id")
    private Long fileNodeId;

    @ApiModelProperty("当前阶段 parse/chunk/embed/index/done")
    private String stage;

    @ApiModelProperty("解析状态 pending/processing/success/failed")
    private String status;

    @ApiModelProperty("最近一次失败原因")
    private String errorMsg;

    @ApiModelProperty("解析产物JSON地址")
    private String parseResultUrl;

    @ApiModelProperty("已写入检索索引的Chunk数")
    private Integer indexedChunkCount;

    @ApiModelProperty("索引同步状态 none/syncing/synced/failed")
    private String indexSyncStatus;

    @ApiModelProperty("本任务解析代际")
    private String parseGeneration;

    @ApiModelProperty("本任务索引代际")
    private String indexGeneration;

    @ApiModelProperty("解析检索服务内部任务ID")
    private String engineTaskId;

    @ApiModelProperty("本任务实际采用的解析策略配置ID")
    private String parseStrategyConfigId;

    @ApiModelProperty("本任务模型配置JSON快照")
    private String modelProfile;

    @ApiModelProperty("是否开启多模态解析 0/1（创建任务时从文件节点固化快照）")
    private Integer multimodalEnabled;
}
