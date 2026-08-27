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
 * 知识库-标签关联表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_kb_tag")
public class KbKbTag extends BaseEntityFill {

    @ApiModelProperty("主键")
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    @ApiModelProperty("知识库ID")
    private Long kbId;

    @ApiModelProperty("标签ID")
    private Long tagId;
}
