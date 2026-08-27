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
 * 知识库权限分配表
 *
 * @author ludan
 */
@Getter
@Setter
@EqualsAndHashCode(callSuper = false)
@TableName("kb_permission_rule")
public class KbPermissionRule extends BaseEntityFill {

    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    private Long kbId;

    @ApiModelProperty("规则类型 dept/role/user")
    private String ruleType;

    @ApiModelProperty("目标对象ID")
    private String targetId;

    @ApiModelProperty("授予角色 admin/reviewer/editor/readonly")
    private String grantRole;
}
