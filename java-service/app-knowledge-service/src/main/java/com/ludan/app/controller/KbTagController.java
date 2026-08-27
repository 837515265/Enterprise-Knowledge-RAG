package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.entity.KbTag;
import com.ludan.app.service.KbTagService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 知识库标签管理 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/tags")
@Api(tags = "知识库标签管理")
@RequiredArgsConstructor
public class KbTagController {

    private final KbTagService kbTagService;

    @ApiOperation(value = "查询全部标签")
    @GetMapping
    public Result<List<KbTag>> list() {
        return Result.succeed(kbTagService.findAll(), "查询成功");
    }

    @ApiOperation(value = "创建标签")
    @PostMapping
    public Result<KbTag> create(@RequestBody Map<String, String> body) {
        String name = body.get("name");
        if (name == null || name.trim().isEmpty()) {
            return Result.failed("标签名称不能为空");
        }
        KbTag tag = kbTagService.createTag(name.trim());
        return Result.succeed(tag, "创建成功");
    }

    @ApiOperation(value = "删除标签")
    @DeleteMapping("/{tagId}")
    public Result<Void> delete(@PathVariable Long tagId) {
        kbTagService.removeById(tagId);
        return Result.succeed(null, "删除成功");
    }
}
