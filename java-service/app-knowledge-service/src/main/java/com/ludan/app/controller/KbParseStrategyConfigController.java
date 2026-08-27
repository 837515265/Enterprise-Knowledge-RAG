package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.entity.KbParseStrategyConfig;
import com.ludan.app.service.KbParseStrategyConfigService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 解析策略配置 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/parse-strategy-configs")
@Api(tags = "解析策略配置")
@RequiredArgsConstructor
public class KbParseStrategyConfigController {

    private final KbParseStrategyConfigService parseStrategyConfigService;

    @ApiOperation("查询解析策略配置")
    @GetMapping
    public Result<List<KbParseStrategyConfig>> list(@RequestParam Map<String, Object> params) {
        return Result.succeed(parseStrategyConfigService.findList(params), "查询成功");
    }

    @ApiOperation("创建解析策略配置")
    @PostMapping
    public Result<KbParseStrategyConfig> create(@RequestBody KbParseStrategyConfig config) {
        return Result.succeed(parseStrategyConfigService.createConfig(config), "创建成功");
    }

    @ApiOperation("更新解析策略配置")
    @PutMapping("/{id}")
    public Result<Void> update(@PathVariable String id, @RequestBody KbParseStrategyConfig config) {
        parseStrategyConfigService.updateConfig(id, config);
        return Result.succeed(null, "更新成功");
    }

    @ApiOperation("删除解析策略配置")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable String id) {
        parseStrategyConfigService.removeById(id);
        return Result.succeed(null, "删除成功");
    }
}
