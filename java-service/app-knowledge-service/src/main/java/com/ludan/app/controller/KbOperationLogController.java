package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.ludan.app.entity.KbOperationLog;
import com.ludan.app.service.KbOperationLogService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 操作日志 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/knowledge-bases/{kbId}/operation-logs")
@Api(tags = "操作日志")
@RequiredArgsConstructor
public class KbOperationLogController {

    private final KbOperationLogService operationLogService;

    @ApiOperation("查询操作日志")
    @GetMapping
    public PageResult<KbOperationLog> list(@PathVariable Long kbId, @RequestParam Map<String, Object> params) {
        params.put("kbId", kbId);
        Page<KbOperationLog> page = operationLogService.findList(params);
        return PageResult.<KbOperationLog>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }
}
