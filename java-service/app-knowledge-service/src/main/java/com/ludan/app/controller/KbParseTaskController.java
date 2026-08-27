package com.ludan.app.controller;

import com.central.common.model.Result;
import com.ludan.app.service.KbParseTaskQueryService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 解析任务进度查询：转发 app-rag-doc parse-service。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb")
@Api(tags = "解析任务")
@RequiredArgsConstructor
public class KbParseTaskController {

    private final KbParseTaskQueryService parseTaskQueryService;

    @ApiOperation("查询解析任务列表（转发 app-rag-doc）")
    @GetMapping("/parse-tasks")
    public Result<List<Map<String, Object>>> listParseTasks(
            @ApiParam("任务状态") @RequestParam(value = "status", required = false) String status,
            @ApiParam("知识库 ID") @RequestParam(value = "kb_id", required = false) Long kbId,
            @ApiParam("文件节点 ID") @RequestParam(value = "file_node_id", required = false) Long fileNodeId,
            @ApiParam("返回条数，默认 20，最大 100") @RequestParam(value = "limit", required = false) Integer limit) {
        try {
            List<Map<String, Object>> list = parseTaskQueryService.listParseTasks(status, kbId, fileNodeId, limit);
            return Result.succeed(list, "查询成功");
        } catch (RuntimeException e) {
            log.warn("查询解析任务列表失败: {}", e.getMessage());
            return Result.failed(e.getMessage());
        }
    }
}
