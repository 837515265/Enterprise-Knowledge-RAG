package com.ludan.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import com.central.common.model.BaseEntityFill;
import io.swagger.annotations.ApiModelProperty;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

/**
 * 检索策略配置
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_retrieval_strategy_config")
public class KbRetrievalStrategyConfig extends BaseEntityFill {

    @ApiModelProperty("主键，策略配置ID")
    @TableId(type = IdType.INPUT)
    private String id;

    @ApiModelProperty("配置名称")
    private String name;

    @ApiModelProperty("策略编码")
    private String code;

    @ApiModelProperty("作用域 template=模板 kb=知识库自定义")
    private String scopeType;

    @ApiModelProperty("所属知识库ID")
    private Long kbId;

    @ApiModelProperty("检索策略参数JSON")
    private String configJson;

    @ApiModelProperty("状态 active/disabled")
    private String status;

    @ApiModelProperty("备注")
    private String remark;

    @TableLogic
    private Integer delFlag;
}
