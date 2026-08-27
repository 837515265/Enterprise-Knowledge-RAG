package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.entity.KbRetrievalStrategyConfig;
import com.ludan.app.service.KbRetrievalStrategyConfigService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 检索策略配置 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/retrieval-strategy-configs")
@Api(tags = "检索策略配置")
@RequiredArgsConstructor
public class KbRetrievalStrategyConfigController {

    private final KbRetrievalStrategyConfigService retrievalStrategyConfigService;

    @ApiOperation("查询检索策略配置")
    @GetMapping
    public Result<List<KbRetrievalStrategyConfig>> list(@RequestParam Map<String, Object> params) {
        return Result.succeed(retrievalStrategyConfigService.findList(params), "查询成功");
    }

    @ApiOperation("创建检索策略配置")
    @PostMapping
    public Result<KbRetrievalStrategyConfig> create(@RequestBody KbRetrievalStrategyConfig config) {
        return Result.succeed(retrievalStrategyConfigService.createConfig(config), "创建成功");
    }

    @ApiOperation("更新检索策略配置")
    @PutMapping("/{id}")
    public Result<Void> update(@PathVariable String id, @RequestBody KbRetrievalStrategyConfig config) {
        retrievalStrategyConfigService.updateConfig(id, config);
        return Result.succeed(null, "更新成功");
    }

    @ApiOperation("删除检索策略配置")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable String id) {
        retrievalStrategyConfigService.removeById(id);
        return Result.succeed(null, "删除成功");
    }
}
