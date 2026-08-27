package com.ludan.app.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.dto.resp.KbListRespDTO;
import com.ludan.app.service.KbKnowledgeBaseService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

/**
 * 知识广场 Controller
 *
 * @author ludan
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/kb/plaza")
@Api(tags = "知识广场")
@RequiredArgsConstructor
public class KbPlazaController {

    private final KbKnowledgeBaseService knowledgeBaseService;

    @ApiOperation("广场列表（只展示公开知识库）")
    @GetMapping
    public PageResult<KbListRespDTO> plazaList(@RequestParam Map<String, Object> params) {
        params.put("visibility", "public");
        params.put("status", "active");
        Page<KbListRespDTO> page = knowledgeBaseService.findList(params);
        return PageResult.<KbListRespDTO>builder()
                .data(page.getRecords())
                .code(0)
                .count(page.getTotal())
                .build();
    }
}
