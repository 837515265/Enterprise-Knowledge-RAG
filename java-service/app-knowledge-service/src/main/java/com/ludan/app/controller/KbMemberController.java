package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.entity.KbPermissionRule;
import com.ludan.app.service.KbPermissionService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库成员管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases/{kbId}/members")
@Api(tags = "知识库成员管理")
@RequiredArgsConstructor
public class KbMemberController {

    private final KbPermissionService permissionService;

    @ApiOperation("查询成员列表")
    @GetMapping
    public Result<List<KbPermissionRule>> list(@PathVariable Long kbId) {
        return Result.succeed(permissionService.getMembers(kbId), "查询成功");
    }

    @ApiOperation("添加成员")
    @PostMapping
    public Result<KbPermissionRule> add(@PathVariable Long kbId, @RequestBody Map<String, String> body) {
        String ruleType = body.get("ruleType");
        String targetId = body.get("targetId");
        String grantRole = body.get("grantRole");
        KbPermissionRule rule = permissionService.addMember(kbId, ruleType, targetId, grantRole);
        return Result.succeed(rule, "添加成功");
    }

    @ApiOperation("移除成员")
    @DeleteMapping("/{ruleId}")
    public Result<Void> remove(@PathVariable Long kbId, @PathVariable Long ruleId) {
        permissionService.removeById(ruleId);
        return Result.succeed(null, "移除成功");
    }
}
